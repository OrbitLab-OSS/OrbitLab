from abc import ABC
from typing import Literal, TypeVar
from datetime import UTC, datetime

from pydantic import BaseModel
from redis.asyncio import Redis

from orbitlab.constants import EventStreams
from orbitlab.data_types import EventStatus, WorkflowState
from .events import OrbitLabEvent


class WorkflowPayload(BaseModel):
    state: WorkflowState = WorkflowState.PENDING


_PL = TypeVar("_PL", bound=WorkflowPayload)

class Workflow(ABC):
    TYPE: str
    SCHEMA: str
    PAYLOAD: type[WorkflowPayload]

    def __init__(self, redis: Redis, event: OrbitLabEvent) -> None:
        """Initialize the workflow."""
        self.redis = redis
        self.event = event

    async def _get_payload_(self) -> WorkflowPayload:
        data: bytes = await self.redis.get(name=self.event.redis_key)
        return self.PAYLOAD.model_validate_json(data.decode())

    async def progress(self, payload: _PL) -> _PL:
        match payload.state:
            case WorkflowState.PENDING:
                payload.state = WorkflowState.VALIDATING
            case WorkflowState.VALIDATING:
                payload.state = WorkflowState.PROVISIONING
            case WorkflowState.PROVISIONING:
                payload.state = WorkflowState.CONFIGURING
            case WorkflowState.CONFIGURING:
                payload.state = WorkflowState.FINALIZING
            case WorkflowState.FINALIZING:
                payload.state = WorkflowState.SUCCEEDED
        return payload

    async def failed(self, error: str, payload: _PL) -> _PL:
        payload.state = WorkflowState.FAILED
        return payload

    async def log(self, level: Literal["Info", "Warning", "Error"], message: str) -> None:
        print({"timestamp": datetime.now(UTC).isoformat(), "level": level, "node": "pve-1-2", "message": message})
        # await self.redis.xadd(
        #     "ol:audit",
        #     {"timestamp": datetime.now(UTC).isoformat(), "level": level, "node": "pve-1-2", "message": message},
        #     maxlen=100_000,
        #     approximate=True,
        # )

    async def transition(self, payload: WorkflowPayload) -> None:
        await self.log(level="Info", message=f"Transitioning {self.event.redis_key} to {payload.state}")
        await self.redis.set(name=self.event.redis_key, value=payload.model_dump_json())
        await self.redis.xadd(name=EventStreams.EVENTS, fields=self.event.model_dump()) # pyright: ignore[reportArgumentType]

    async def pending(self, payload: WorkflowPayload) -> WorkflowPayload:
        payload.state = WorkflowState.VALIDATING
        return payload

    async def validate(self, payload: WorkflowPayload) -> WorkflowPayload:
        payload.state = WorkflowState.PROVISIONING
        return payload

    async def provision(self, payload: WorkflowPayload) -> WorkflowPayload:
        payload.state = WorkflowState.CONFIGURING
        return payload

    async def configure(self, payload: WorkflowPayload) -> WorkflowPayload:
        payload.state = WorkflowState.FINALIZING
        return payload

    async def finalize(self, payload: WorkflowPayload) -> WorkflowPayload:
        payload.state = WorkflowState.SUCCEEDED
        return payload

    async def on_succeed(self, payload: WorkflowPayload) -> None:
        pass

    async def on_failure(self, payload: WorkflowPayload) -> None:
        pass

    async def run_once(self) -> None:
        try:
            payload = await self._get_payload_()
            match payload.state:
                case WorkflowState.PENDING:
                    payload = await self.pending(payload=payload)
                    await self.transition(payload=payload)

                case WorkflowState.VALIDATING:
                    payload = await self.validate(payload=payload)
                    await self.transition(payload=payload)

                case WorkflowState.PROVISIONING:
                    payload = await self.provision(payload=payload)
                    await self.transition(payload=payload)

                case WorkflowState.CONFIGURING:
                    payload = await self.configure(payload=payload)
                    await self.transition(payload=payload)

                case WorkflowState.FINALIZING:
                    payload = await self.finalize(payload=payload)
                    await self.transition(payload=payload)

                case WorkflowState.SUCCEEDED:
                    await self.on_succeed(payload=payload)
                    self.event.status = EventStatus.SUCCEEDED
                    await self.transition(payload=payload)
                
                case WorkflowState.FAILED:
                    await self.on_failure(payload=payload)
                    self.event.status = EventStatus.FAILED
                    await self.transition(payload=payload)

        except Exception as err:
            payload = await self.failed(error=f"Encountered unexpected error: {err}", payload=payload)
            await self.transition(payload=payload)
