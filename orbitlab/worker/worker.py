import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import uuid

from redis.asyncio import Redis
from orbitlab.constants import EventStreams
from orbitlab.data_types import EventStatus
from orbitlab.worker.workflows.base import Workflow, WorkflowPayload
from orbitlab.worker.workflows.events import OrbitLabEvent
from orbitlab.worker.workflows import workflows


class WorkflowRegistry:
    """OrbitLab Workflow Registry used by the Worker to execute workflows from events."""

    def __init__(self) -> None:
        """Initialize workflow registry."""
        self._registry: dict[tuple[str, str], type[Workflow]] = {}

    def register(self, workflow_cls: type[Workflow]) -> None:
        """Register workflow class based on event type and schema version."""
        key = (workflow_cls.TYPE, workflow_cls.SCHEMA)
        if key in self._registry:
            _type, schema = key
            msg = f"Duplicate workflow registered: {_type}@{schema}"
            raise RuntimeError(msg)
        self._registry[key] = workflow_cls

    def resolve(self, *, event: OrbitLabEvent) -> type[Workflow]:
        """Resolve event to workflow class."""
        try:
            return self._registry[(event.name, event.version)]
        except KeyError as err:
            msg = f"No workflow registered for {event.name}@{event.version}"
            raise RuntimeError(msg) from err


type StreamEventData = tuple[bytes, dict[bytes, bytes]]
type RedisStreamEvent = tuple[bytes, tuple[StreamEventData]]

class Worker:
    """OrbitLab Event Worker."""

    def __init__(self) -> None:
        """Initialize the worker."""
        self.redis = Redis(host="192.168.87.230", port=6379)
        self.task: asyncio.Task | None = None
        self.event = asyncio.Event()
        self.registry = WorkflowRegistry()
        self._workflows = set()
        self._register_workflows_()

    def _register_workflows_(self) -> None:
        for workflow in workflows:
            self.registry.register(workflow)

    async def _parse_event_(self, stream_event: RedisStreamEvent) -> OrbitLabEvent:
        _, event_data = stream_event
        _event_data = event_data[0]
        _, payload = _event_data
        return OrbitLabEvent.model_validate({key.decode(): value.decode() for key, value in payload.items()})

    async def _handle_event(self, event: OrbitLabEvent) -> None:
        if event.status in (EventStatus.SUCCEEDED, EventStatus.FAILED):
            print(event.status, event.redis_key)
            self.redis.xdel(name=event.redis_key)
        else:
            workflow_cls = self.registry.resolve(event=event)
            workflow = asyncio.create_task(workflow_cls(redis=self.redis, event=event).run_once())
            self._workflows.add(workflow)
            workflow.add_done_callback(self._workflows.discard)

    async def _run_(self) -> None:
        while True:
            try:
                stream_events = await self.redis.xreadgroup(
                    groupname="ol:workers",
                    consumername="pve-1-2",
                    streams={EventStreams.EVENTS: ">"},
                    count=1,
                )
                if stream_events:
                    event = await self._parse_event_(stream_event=stream_events[0])
                    await self._handle_event(event=event)
                if self.event.is_set():
                    print("Exiting...")
                    break
                await asyncio.sleep(1)
            except Exception as err:
                print(err)

    @classmethod
    async def create_workflow(cls, workflow: type[Workflow], payload: WorkflowPayload) -> None:
        redis = Redis(host="192.168.87.230", port=6379)
        event = OrbitLabEvent(
            name=workflow.TYPE,
            version=workflow.SCHEMA,
            job_id=str(uuid.uuid4()),
            status=EventStatus.IN_PROGRESS,
        )
        await redis.set(name=event.redis_key, value=payload.model_dump_json())
        await redis.xadd(name=EventStreams.EVENTS, fields=event.model_dump()) # pyright: ignore[reportArgumentType]
        await redis.xadd(
            "ol:audit",
            {"timestamp": datetime.now(UTC).isoformat(), "level": "Info", "node": "pve-1-2", "message": f"Creating workflow "},
            maxlen=100_000,
            approximate=True,
        )

    @asynccontextmanager
    async def start(self):
        self.task = asyncio.create_task(self._run_())
        yield
        self.event.set()
        await asyncio.gather(self.task)
        print("Worker Exited.")
