"""Workflow Base."""

from datetime import UTC, datetime
import os
from typing import Literal

from pydantic import BaseModel, model_validator
from redis.asyncio import Redis

from orbitlab.constants import EventStreams
from orbitlab.data_types import EventStatus, WorkflowStatus
from orbitlab.worker.events import WorkflowEvent


class WorkflowPayload(BaseModel):
    """Payload base for a durable work/commit event chain.

    ``step`` names the unit of work and ``phase`` makes its external work and
    Redis commit separate stream events.  This intentionally replaces the
    former workflow-status state machine: a worker never advances a workflow
    in memory across a boundary that has not been committed and re-enqueued.
    """

    step: Literal["validate", "provision", "configure", "finalize", "succeeded", "failed"] = "validate"
    phase: Literal["work", "commit"] = "work"
    result: EventStatus | None = None
    id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_status_payload(cls, value: object) -> object:
        """Read state-machine payloads left by an interrupted prior release."""
        if not isinstance(value, dict) or "step" in value:
            return value
        state = str(value.pop("state", WorkflowStatus.PENDING)).lower()
        steps = {
            "pending": "validate",
            "validating": "validate",
            "provisioning": "provision",
            "configuring": "configure",
            "finalizing": "finalize",
            "succeeded": "succeeded",
            "failed": "failed",
        }
        value["step"] = steps.get(state, "validate")
        value["phase"] = "work"
        if state == "succeeded":
            value["result"] = EventStatus.SUCCEEDED
        elif state == "failed":
            value["result"] = EventStatus.FAILED
        return value

class Workflow:
    """Base class for workflows composed as explicit Redis work/commit events."""

    TYPE: str
    SCHEMA: str
    PAYLOAD_TYPE: type[WorkflowPayload]
    payload: WorkflowPayload

    def __init__(self, redis: Redis, event: "WorkflowEvent") -> None:
        """Initialize the workflow."""
        self.redis = redis
        self.event = event

    async def _get_payload(self) -> WorkflowPayload:
        """Retrieve and validate the workflow payload from Redis storage."""
        data: bytes = await self.redis.get(name=self.event.redis_key)
        if not data:
            raise ValueError
        return self.PAYLOAD_TYPE.model_validate_json(data.decode())

    def _redact_params(self, params: dict) -> dict:
        redactable = ("cipassword", "password", "ssh-public-keys")
        return {k: "*****" if k in redactable else v for k, v in params.items()}

    def _event_for_payload(self) -> WorkflowEvent:
        """Annotate stream messages with the durable step they represent."""
        return self.event.model_copy(update={"step": self.payload.step, "phase": self.payload.phase})

    async def _transition(self) -> None:
        """Commit a phase result and emit exactly one next workflow event."""
        await self.log(level="Debug", message=f"Committing {self.event.redis_key}: {self.payload.step}/{self.payload.phase}")
        event = self._event_for_payload()
        async with self.redis.pipeline(transaction=True) as pipeline:
            pipeline.set(name=self.event.redis_key, value=self.payload.model_dump_json())
            pipeline.xadd(
                name=EventStreams.WORKFLOWS,
                fields=event.model_dump(), # pyright: ignore[reportArgumentType]
                maxlen=5000,
                approximate=True,
            )
            await pipeline.execute()

    async def _end_transition(self) -> None:
        """Commit terminal job status and retire its transient payload."""
        event = self._event_for_payload()
        async with self.redis.pipeline(transaction=True) as pipeline:
            pipeline.delete(self.event.redis_key)
            pipeline.xadd(
                name=EventStreams.WORKFLOWS,
                fields=event.model_dump(), # pyright: ignore[reportArgumentType]
                maxlen=5000,
                approximate=True,
            )
            await pipeline.execute()

    async def run_once(self) -> None:
        """Run one durable work or commit phase and never chain phases in memory."""
        try:
            self.payload = await self._get_payload()
            if self.payload.phase == "work":
                await self._work()
            else:
                await self._commit()

        except Exception as err:  # noqa: BLE001
            print(self, err)
            if self.event.status != EventStatus.FAILED:
                await self.fail(f"Encountered unexpected error: {err}")
                self.payload.phase = "commit"
                await self._transition()
        
        finally:
            if self.event.status in (EventStatus.FAILED, EventStatus.SUCCEEDED):
                await self._end_transition()

    async def _work(self) -> None:
        """Execute one side-effecting step, then enqueue its commit phase."""
        match self.payload.step:
            case "validate":
                await self.validate()
            case "provision":
                await self.provision()
            case "configure":
                await self.configure()
            case "finalize":
                await self.finalize()
            case "succeeded":
                await self.on_succeed()
            case "failed":
                await self.on_failure()
        self.payload.phase = "commit"
        await self._transition()

    async def _commit(self) -> None:
        """Persist a work result and emit the next work event or final job event."""
        if self.payload.step == "succeeded" and self.payload.result == EventStatus.SUCCEEDED:
            self.event.status = EventStatus.SUCCEEDED
            return
        if self.payload.step == "failed" and self.payload.result == EventStatus.FAILED:
            self.event.status = EventStatus.FAILED
            return

        if self.payload.result == EventStatus.FAILED:
            self.payload.step = "failed"
        elif self.payload.result == EventStatus.SUCCEEDED:
            self.payload.step = "succeeded"
        else:
            steps: dict[str, str] = {
                "validate": "provision",
                "provision": "configure",
                "configure": "finalize",
                "finalize": "succeeded",
            }
            self.payload.step = steps[self.payload.step]
        self.payload.phase = "work"
        await self._transition()

    async def fail(self, error: str) -> None:
        """Record a failed work result; the following commit emits failure work."""
        await self.log(level="Error", message=error)
        self.payload.result = EventStatus.FAILED

    async def succeed(self, message: str, *, notify: bool = True) -> None:
        """Record a successful short-circuit result for the following commit."""
        await self.log(message=message)
        self.payload.result = EventStatus.SUCCEEDED

    async def log(self, message: str, level: Literal["Debug", "Info", "Warning", "Error"] = "Info") -> None:
        """Log a message with a specified level and message content."""
        if os.environ.get("ORBITLAB_DEV"):
            print(f"{datetime.now(UTC).isoformat()} - {level} - {self.event.workflow_id} - {message}")
        if level == "Debug" and not os.environ.get("ORBITLAB_DEV"):
            return
        await self.redis.xadd(
            name=EventStreams.WORKFLOW_LOGS,
            fields={
                "timestamp": datetime.now(UTC).isoformat(),
                "level": level,
                "workflow": self.event.workflow_id,
                "message": message,
            },
            maxlen=5000,
            approximate=True,
        )

    async def validate(self) -> None:
        """Handle the VALIDATING state, then transition the workflow to PROVISIONING."""

    async def provision(self) -> None:
        """Handle the PROVISIONING state, then transition the workflow to CONFIGURING."""

    async def configure(self) -> None:
        """Handle the CONFIGURING state, then transition the workflow to FINALIZING."""

    async def finalize(self) -> None:
        """Handle the FINALIZING state, then transition the workflow to SUCCEEDED."""

    async def on_succeed(self) -> None:
        """Handle actions to perform when the workflow succeeds."""

    async def on_failure(self) -> None:
        """Handle actions to perform when the workflow fails."""
