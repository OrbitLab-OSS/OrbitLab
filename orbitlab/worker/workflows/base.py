"""Workflow Base."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal, TypeVar

import reflex as rx
from pydantic import BaseModel
from redis.asyncio import Redis

from orbitlab.constants import EventStreams
from orbitlab.data_types import EventStatus, WorkflowState
from orbitlab.worker.events import WorkflowEvent


class DuplicateWorkflowError(Exception):
    """Exception raised when attempting to create a duplicate workflow."""

    def __init__(self, lock_id: str) -> None:
        """Initialize the DuplicateWorkflowError with a lock ID."""
        super().__init__(f"Duplicate workflow: {lock_id}")
        self.lock_id = lock_id


class WorkflowPayload(BaseModel):
    """Payload base model for workflow state management."""

    state: WorkflowState = WorkflowState.PENDING
    lock_id: str = ""


_PL = TypeVar("_PL", bound=WorkflowPayload)
_DT = TypeVar("_DT")

class Workflow:
    """Base class for workflow implementations, providing state management and event handling."""

    TYPE: str
    SCHEMA: str
    PAYLOAD_TYPE: type[WorkflowPayload]
    payload: _PL

    TTL: int = 300
    IDP_TOKEN: str = ""

    def __init__(self, redis: Redis, event: "WorkflowEvent") -> None:
        """Initialize the workflow."""
        self.redis = redis
        self.event = event

    async def _get_payload(self) -> WorkflowPayload:
        """Retrieve and validate the workflow payload from Redis storage."""
        data: bytes = await self.redis.get(name=self.event.redis_key)
        return self.PAYLOAD_TYPE.model_validate_json(data.decode())

    async def _aquire_lock(self) -> None:
        if self.IDP_TOKEN:
            while not bool(await self.redis.set(name=self.IDP_TOKEN, value="1", nx=True, ex=self.TTL)):
                await self.log(f"Waiting for {self.IDP_TOKEN} lock...")
                await asyncio.sleep(2)
            self.payload.lock_id = self.IDP_TOKEN
            return

        data = self.payload.model_dump(exclude_none=True, exclude=["state", "lock_id"])
        canonical = json.dumps(
            {
                "name": self.TYPE,
                "version": self.SCHEMA,
                "payload": json.dumps(data, sort_keys=True, separators=(",", ":")),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        self.payload.lock_id = hashlib.sha256(canonical.encode()).hexdigest()
        await self.log(f"Acquiring Lock: {self.payload.lock_id}")
        if not bool(await self.redis.set(name=self.payload.lock_id, value="1", nx=True, ex=self.TTL)):
            raise DuplicateWorkflowError(lock_id=self.payload.lock_id)

    async def _release_lock(self, lock_id: str) -> None:
        if lock_id:
            await self.log(f"Releasing Lock: {lock_id}")
            await self.redis.delete(lock_id)

    async def _create_new_workflow(self, workflow: type["Workflow"], payload: WorkflowPayload) -> None:
        """Create a new workflow instance with the given payload and emit a creation event."""
        event = WorkflowEvent(name=workflow.TYPE, version=workflow.SCHEMA)
        await self.redis.set(name=event.redis_key, value=payload.model_dump_json())
        await self.log(f"Creating workflow {event.workflow_id}")
        response = await self.redis.xadd(
            name=EventStreams.WORKFLOWS,
            fields=event.model_dump(),
            maxlen=5000,
            approximate=True,
        )
        print(response)

    async def _transition(self) -> None:
        """Log the state transition, update the workflow payload in Redis, and emit an event."""
        await self.log(level="Info", message=f"Transitioning {self.event.redis_key} to {self.payload.state}")
        await self.redis.set(name=self.event.redis_key, value=self.payload.model_dump_json())
        await self.redis.xadd(
            name=EventStreams.WORKFLOWS,
            fields=self.event.model_dump(),
            maxlen=5000,
            approximate=True,
        )  # pyright: ignore[reportArgumentType]

    async def _end_transition(self) -> None:
        """Delete the workflow payload from Redis and emit a final workflow event."""
        await self.redis.delete(self.event.redis_key)
        await self.redis.xadd(
            name=EventStreams.WORKFLOWS,
            fields=self.event.model_dump(),
            maxlen=5000,
            approximate=True,
        )

    async def get_redis_hash_value(self, name: str, key: str, *, value_type: type[_DT] = str) -> _DT:
        value: bytes = await self.redis.hget(name=name, key=key)
        return value_type(value.decode())

    async def set_redis_hash_value(self, name: str, key: str, value: Any) -> None:
        await self.redis.hset(name=name, key=key, value=str(value)) 

    async def run_once(self) -> None:  # noqa: C901, PLR0912
        """Run a single workflow step based on the current payload state, handling transitions and exceptions."""
        try:
            self.payload = await self._get_payload()
            match self.payload.state:
                case WorkflowState.PENDING:
                    await self._aquire_lock()
                    self.payload.state = WorkflowState.VALIDATING
                    await self._transition()

                case WorkflowState.VALIDATING:
                    await self.validate()
                    if self.payload.state == WorkflowState.VALIDATING:
                        self.payload.state = WorkflowState.PROVISIONING
                    await self._transition()

                case WorkflowState.PROVISIONING:
                    await self.provision()
                    if self.payload.state == WorkflowState.PROVISIONING:
                        self.payload.state = WorkflowState.CONFIGURING
                    await self._transition()

                case WorkflowState.CONFIGURING:
                    await self.configure()
                    if self.payload.state == WorkflowState.CONFIGURING:
                        self.payload.state = WorkflowState.FINALIZING
                    await self._transition()

                case WorkflowState.FINALIZING:
                    await self.finalize()
                    if self.payload.state == WorkflowState.FINALIZING:
                        self.payload.state = WorkflowState.SUCCEEDED
                    await self._transition()

                case WorkflowState.SUCCEEDED:
                    await self.on_succeed()
                    await self._release_lock(lock_id=self.payload.lock_id)
                    self.event.status = EventStatus.SUCCEEDED
                    await self._end_transition()

                case WorkflowState.FAILED:
                    await self.on_failure()
                    await self._release_lock(lock_id=self.payload.lock_id)
                    self.event.status = EventStatus.FAILED
                    await self._end_transition()

        except DuplicateWorkflowError as err:
            await self.log(f"Duplicate Workflow: {err.lock_id}")
            self.event.status = EventStatus.FAILED
            await self._end_transition()

        except Exception as err:  # noqa: BLE001
            print(err)
            await self.fail(f"Encountered unexpected error: {err}")
            await self._transition()

    async def fail(self, error: str) -> None:
        """Handle workflow failure by logging the error and updating the payload state to FAILED."""
        await self.log(level="Error", message=error)
        self.payload.state = WorkflowState.FAILED

    async def succeed(self, message: str) -> None:
        """Handle workflow success by logging the message and updating the payload state to SUCCEEDED."""
        await self.log(message=message)
        await self.emit_reflex_events(events=[rx.toast.success(message=message)])
        self.payload.state = WorkflowState.SUCCEEDED

    async def log(self, message: str, level: Literal["Info", "Warning", "Error"] = "Info") -> None:
        """Log a message with a specified level and message content."""
        print(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": level,
                "workflow": self.event.workflow_id,
                "message": message,
            },
        )

    async def validate(self) -> None:
        """Handle the VALIDATING state, then transition the workflow to PROVISIONING."""
        self.payload.state = WorkflowState.PROVISIONING

    async def provision(self) -> None:
        """Handle the PROVISIONING state, then transition the workflow to CONFIGURING."""
        self.payload.state = WorkflowState.CONFIGURING

    async def configure(self) -> None:
        """Handle the CONFIGURING state, then transition the workflow to FINALIZING."""
        self.payload.state = WorkflowState.FINALIZING

    async def finalize(self) -> None:
        """Handle the FINALIZING state, then transition the workflow to SUCCEEDED."""
        self.payload.state = WorkflowState.SUCCEEDED

    async def on_succeed(self) -> None:
        """Handle actions to perform when the workflow succeeds."""

    async def on_failure(self) -> None:
        """Handle actions to perform when the workflow fails."""
