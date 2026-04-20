"""OrbitLab Event Worker."""

import asyncio
from functools import cached_property
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import sys

from pydantic import ValidationError
from redis.exceptions import ResponseError

from orbitlab.constants import EventStreams
from orbitlab.data_types import EventStatus, RedisStreamEvent
from orbitlab.proxmox import Proxmox
from orbitlab.web.utilities import get_redis
from orbitlab.worker import workflows
from orbitlab.worker.events import OrbitLabEvent, WorkflowEvent


class WorkflowRegistry:
    """OrbitLab Workflow Registry used by the Worker to execute workflows from events."""

    def __init__(self) -> None:
        """Initialize workflow registry."""
        self._registry: dict[tuple[str, str], type[workflows.Workflow]] = {}

    def register(self, workflow_cls: type[workflows.Workflow]) -> None:
        """Register workflow class based on event type and schema version."""
        key = (workflow_cls.TYPE, workflow_cls.SCHEMA)
        if key in self._registry:
            _type, schema = key
            msg = f"Duplicate workflow registered: {_type}@{schema}"
            raise RuntimeError(msg)
        self._registry[key] = workflow_cls

    def resolve(self, *, event: WorkflowEvent) -> type[workflows.Workflow] | None:
        """Resolve event to workflow class."""
        try:
            return self._registry[(event.name, event.version)]
        except KeyError:
            return None


def _register_workflows_() -> WorkflowRegistry:
    registry = WorkflowRegistry()
    for workflow in workflows.workflows:
        registry.register(workflow)
    return registry


class Worker:
    """OrbitLab Event Worker."""

    registry = _register_workflows_()

    def __init__(self) -> None:
        """Initialize the worker."""
        self.task: asyncio.Task | None = None
        self._event = asyncio.Event()
        self._workflows = set()
        self.redis = get_redis()

    @cached_property
    def node(self) -> str:
        return Proxmox().__node__

    async def _parse_workflow_event(self, stream_event: RedisStreamEvent) -> WorkflowEvent:
        _, event_data = stream_event
        _event_data = event_data[0]
        _, payload = _event_data
        return WorkflowEvent.model_validate({key.decode(): value.decode() for key, value in payload.items()})

    async def _handle_workflow_event(self, event: WorkflowEvent) -> None:
        if event.status in (EventStatus.SUCCEEDED, EventStatus.FAILED):
            self.redis.xdel(name=event.redis_key)
        elif workflow_cls := self.registry.resolve(event=event):
            workflow = asyncio.create_task(workflow_cls(redis=self.redis, event=event).run_once())
            self._workflows.add(workflow)
            workflow.add_done_callback(self._workflows.discard)
        else:
            await self.redis.xadd(
                name=EventStreams.SYSTEM_LOGS,
                fields={
                    "timestamp": datetime.now(UTC).isoformat(),
                    "level": "Error",
                    "trace": "worker.worker.Worker._handle_workflow_event",
                    "message": str(event),
                },
                maxlen=5000,
                approximate=True,
            )

    async def _ensure_group(self, group: str, stream: str) -> None:
        try:
            stream_groups = await self.redis.xinfo_groups(name=stream)
            for stream_group in stream_groups:
                if stream_group["name"].decode() == group:
                    return
        except ResponseError as err:
            if "no such key" not in str(err):
                raise
        await self.redis.xgroup_create(name=stream, groupname=group, mkstream=True)

    async def _process_workflows(self) -> None:
        await self._ensure_group(group="ol:workers", stream=EventStreams.WORKFLOWS)
        while True:
            try:
                stream_events = await self.redis.xreadgroup(
                    groupname="ol:workers",
                    consumername="pve-1-2",
                    streams={EventStreams.WORKFLOWS: ">"},
                    count=1,
                )
                if stream_events:
                    event = await self._parse_workflow_event(stream_event=stream_events[0])
                    await self._handle_workflow_event(event=event)
                if self._event.is_set():
                    sys.stdout.write("Exiting Workflow Stream...\n")
                    break
                await asyncio.sleep(1)
            except Exception as err:  # noqa: BLE001
                await self.redis.xadd(
                    name=EventStreams.SYSTEM_LOGS,
                    fields={
                        "timestamp": datetime.now(UTC).isoformat(),
                        "level": "Error",
                        "trace": "worker.worker.Worker._process_workflows",
                        "message": str(err),
                    },
                    maxlen=5000,
                    approximate=True,
                )

    async def _process_events(self) -> None:
        await self._ensure_group(group="ol:workers", stream=EventStreams.EVENTS)
        while True:
            try:
                stream_events = await self.redis.xreadgroup(
                    groupname="ol:workers",
                    consumername=self.node,
                    streams={EventStreams.EVENTS: ">"},
                    count=1,
                )
                if stream_events:
                    event = OrbitLabEvent.parse_from_redis(stream_events[0])
                    if error := await self.create_workflow(
                        name=event.event, version=event.version, payload=event.payload,
                    ):
                        await self.redis.xadd(
                            name=EventStreams.SYSTEM_LOGS,
                            fields={
                                "timestamp": datetime.now(UTC).isoformat(),
                                "level": "Error",
                                "trace": "worker.worker.Worker._process_events",
                                "message": error,
                            },
                            maxlen=5000,
                            approximate=True,
                        )
                if self._event.is_set():
                    sys.stdout.write("Exiting Event Stream...\n")
                    break
                await asyncio.sleep(1)
            except Exception as err:  # noqa: BLE001
                await self.redis.xadd(
                    name=EventStreams.SYSTEM_LOGS,
                    fields={
                        "timestamp": datetime.now(UTC).isoformat(),
                        "level": "Error",
                        "trace": "worker.worker.Worker._process_workflows",
                        "message": str(err),
                    },
                    maxlen=5000,
                    approximate=True,
                )

    @classmethod
    async def create_workflow(cls, name: str, version: str, payload: dict) -> str:
        """Create and enqueue a new workflow event in Redis."""
        event = WorkflowEvent(name=name, version=version)
        if workflow_cls := cls.registry.resolve(event=event):

            try:
                value = workflow_cls.PAYLOAD_TYPE.model_validate(payload)
            except ValidationError as err:
                return str(err)

            redis = get_redis()
            await redis.set(name=event.redis_key, value=value.model_dump_json())
            await redis.xadd(
                name=EventStreams.WORKFLOWS,
                fields=event.model_dump(),
                maxlen=5000,
                approximate=True,
            )  # pyright: ignore[reportArgumentType]
            await redis.xadd(
                name=EventStreams.SYSTEM_LOGS,
                fields={
                    "timestamp": datetime.now(UTC).isoformat(),
                    "level": "Info",
                    "trace": "web.utilities.get_redis_value",
                    "message": f"Creating workflow {event.redis_key}",
                },
                maxlen=5000,
                approximate=True,
            )
            return ""
        return f"Workflow {event.name}@{event.version} does not exist"

    @asynccontextmanager
    async def start(self) -> AsyncGenerator[None, None]:
        """Start the worker event loop as an async context manager."""
        workflows = asyncio.create_task(self._process_workflows())
        events = asyncio.create_task(self._process_events())
        yield
        self._event.set()
        await asyncio.gather(workflows, events)
        sys.stdout.write("Worker Exited.\n")
