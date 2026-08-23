"""OrbitLab Event Worker."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import cached_property
import os
import sys
from uuid import uuid4

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from orbitlab.constants import EventStreams
from orbitlab.data_types import EventStatus
from orbitlab.proxmox import Proxmox
from orbitlab.worker import workflows
from orbitlab.worker.events import OrbitLabEvent, WorkflowEvent
from orbitlab.worker.jobs import JobStore
from orbitlab.worker.reconciler import ValidationWorker


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

    GROUP_NAME = "ol:workers"
    READ_COUNT = 10
    BLOCK_MS = 5_000
    CLAIM_IDLE_MS = 30_000

    registry = _register_workflows_()

    def __init__(self) -> None:
        """Initialize the worker."""
        self.task: asyncio.Task | None = None
        self._event = asyncio.Event()
        self.redis = self._get_redis()

    @classmethod
    def _get_redis(cls) -> Redis:
        if os.environ.get("ORBITLAB_DEV"):
            return Redis.from_url(os.environ["ORBITLAB_REDIS_URL"])
        return Redis(db=10)

    @cached_property
    def node(self) -> str:
        return Proxmox().__node__

    @staticmethod
    def _decode(value: bytes | str | memoryview) -> str:
        if isinstance(value, memoryview):
            value = value.tobytes()
        if isinstance(value, bytes):
            return value.decode()
        return value

    def _parse_stream_events(self, stream_events: list) -> list[tuple[str, dict[str, str]]]:
        if not stream_events:
            return []
        _, event_data = stream_events[0]
        return [
            (
                self._decode(event_id),
                {self._decode(key): self._decode(value) for key, value in payload.items()},
            )
            for event_id, payload in event_data
        ]

    async def _parse_workflow_event(self, stream_event: tuple[str, dict[str, str]]) -> tuple[str, WorkflowEvent]:
        event_id, payload = stream_event
        return event_id, WorkflowEvent.model_validate(payload)

    async def _read_pending_stream_events(self, stream: str, consumer: str) -> list[tuple[str, dict[str, str]]]:
        _next_start, event_data, _deleted = await self.redis.xautoclaim(
            name=stream,
            groupname=self.GROUP_NAME,
            consumername=consumer,
            min_idle_time=self.CLAIM_IDLE_MS,
            start_id="0-0",
            count=self.READ_COUNT,
        )
        return [
            (
                self._decode(event_id),
                {self._decode(key): self._decode(value) for key, value in payload.items()},
            )
            for event_id, payload in event_data
        ]

    async def _read_stream_events(self, stream: str, consumer: str) -> list[tuple[str, dict[str, str]]]:
        if pending_events := await self._read_pending_stream_events(stream=stream, consumer=consumer):
            return pending_events
        return self._parse_stream_events(
            await self.redis.xreadgroup(
                groupname=self.GROUP_NAME,
                consumername=consumer,
                streams={stream: ">"},
                count=self.READ_COUNT,
                block=self.BLOCK_MS,
            ),
        )

    async def _handle_workflow_event(self, event: WorkflowEvent) -> None:
        """Execute a workflow step before the stream entry is acknowledged."""
        jobs = JobStore(self.redis)
        if event.status in (EventStatus.SUCCEEDED, EventStatus.FAILED):
            await self.redis.delete(event.redis_key)
            await jobs.set_status(str(event.job_id), "succeeded" if event.status == EventStatus.SUCCEEDED else "failed")
        elif workflow_cls := self.registry.resolve(event=event):
            await jobs.set_status(str(event.job_id), "running")
            await workflow_cls(redis=self.redis, event=event).run_once()
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
            await self.redis.xgroup_create(name=stream, groupname=group, mkstream=True)
        except ResponseError as err:
            if "BUSYGROUP" not in str(err):
                raise

    async def _process_workflows(self) -> None:
        consumer = self.node
        await self._ensure_group(group=self.GROUP_NAME, stream=EventStreams.WORKFLOWS)
        while not self._event.is_set():
            try:
                stream_events = await self._read_stream_events(stream=EventStreams.WORKFLOWS, consumer=consumer)
                for stream_event in stream_events:
                    event_id, event = await self._parse_workflow_event(stream_event=stream_event)
                    await self._handle_workflow_event(event=event)
                    await self.redis.xack(EventStreams.WORKFLOWS, self.GROUP_NAME, event_id)
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
        sys.stdout.write("Exiting Workflow Stream...\n")

    async def _process_events(self) -> None:
        consumer = self.node
        await self._ensure_group(group=self.GROUP_NAME, stream=EventStreams.EVENTS)
        while not self._event.is_set():
            try:
                stream_events = await self._read_stream_events(stream=EventStreams.EVENTS, consumer=consumer)
                for event_id, payload in stream_events:
                    event = OrbitLabEvent.model_validate(payload)
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
                    await self.redis.xack(EventStreams.EVENTS, self.GROUP_NAME, event_id)
            except Exception as err:  # noqa: BLE001
                await self.redis.xadd(
                    name=EventStreams.SYSTEM_LOGS,
                    fields={
                        "timestamp": datetime.now(UTC).isoformat(),
                        "level": "Error",
                        "trace": "worker.worker.Worker._process_events",
                        "message": str(err),
                    },
                    maxlen=5000,
                    approximate=True,
                )
        sys.stdout.write("Exiting Event Stream...\n")

    async def _validate_resources(self) -> None:
        """Continuously record observed state without mutating Proxmox."""
        validator = ValidationWorker(self.redis)
        while not self._event.is_set():
            try:
                await validator.run_once()
            except Exception as err:  # noqa: BLE001
                await self.redis.xadd(
                    name=EventStreams.SYSTEM_LOGS,
                    fields={
                        "timestamp": datetime.now(UTC).isoformat(),
                        "level": "Error",
                        "trace": "worker.worker.Worker._validate_resources",
                        "message": str(err),
                    },
                    maxlen=5000,
                    approximate=True,
                )
            try:
                await asyncio.wait_for(self._event.wait(), timeout=ValidationWorker.INTERVAL_SECONDS)
            except TimeoutError:
                continue

    @classmethod
    async def create_workflow(cls, name: str, version: str, payload: dict, *, idempotency_key: str | None = None) -> str:
        """Create and enqueue a new workflow event in Redis."""
        event = WorkflowEvent(name=name, version=version)
        if workflow_cls := cls.registry.resolve(event=event):

            try:
                value = workflow_cls.PAYLOAD_TYPE.model_validate(payload)
            except ValidationError as err:
                return str(err)

            redis = cls._get_redis()
            job = await JobStore(redis).enqueue(
                name=name,
                version=version,
                payload=value.model_dump(mode="json"),
                idempotency_key=idempotency_key or str(uuid4()),
            )
            await redis.xadd(
                name=EventStreams.SYSTEM_LOGS,
                fields={
                    "timestamp": datetime.now(UTC).isoformat(),
                    "level": "Info",
                    "trace": "worker.worker.Worker.create_workflow",
                    "message": f"Created job {job.id} for {job.name}",
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
        validator = asyncio.create_task(self._validate_resources())
        yield
        self._event.set()
        await asyncio.gather(workflows, events, validator)
        sys.stdout.write("Worker Exited.\n")
