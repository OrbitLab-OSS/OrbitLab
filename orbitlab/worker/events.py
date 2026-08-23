"""OrbitLab Events."""

import json
import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, PlainSerializer, field_validator

from orbitlab.data_types import EventStatus, RedisStreamEvent


class WorkflowEvent(BaseModel):
    """Represents a worfklow event in the OrbitLab system."""
    name: str
    version: str
    job_id: Annotated[uuid.UUID, PlainSerializer(str)] = Field(default_factory=uuid.uuid4)
    status: EventStatus = EventStatus.IN_PROGRESS
    step: str = ""
    phase: Literal["", "work", "commit"] = ""

    @property
    def workflow_id(self) -> str:
        """Workflow ID."""
        return f"{self.name}@{self.version}"

    @property
    def redis_key(self) -> str:
        """Generate a Redis key for the event using its name, version, and job ID."""
        return f"ol:{self.name}:{self.version}:{self.job_id}"


class OrbitLabEvent(BaseModel):
    """Represents an relayed OrbitLab."""

    event: str
    version: str
    payload: dict

    @field_validator("payload", mode="plain")
    @classmethod
    def _deserialize_json(cls, payload: str | dict) -> dict:
        if isinstance(payload, str):
            return json.loads(payload)
        return payload

    @classmethod
    def parse_from_redis(cls, stream_event: RedisStreamEvent) -> Self:
        """Parse an OrbitLabEvent from a Redis stream event."""
        _, event_data = stream_event
        _event_data = event_data[0]
        _, emitted_event = _event_data
        return cls.model_validate({k.decode(): v.decode() for k,v in emitted_event.items()})


class NotificationEvent(BaseModel):
    level: Literal["INFO", "WARN", "ERROR"]
    message: str
