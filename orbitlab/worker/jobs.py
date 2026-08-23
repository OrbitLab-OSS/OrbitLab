"""Durable job records and idempotent enqueueing for OrbitLab commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Literal
from uuid import uuid4

from redis.asyncio import Redis

from orbitlab.constants import EventStreams
from orbitlab.worker.events import WorkflowEvent


JobStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass(frozen=True, slots=True)
class Job:
    """The UI-facing durable status of a queued operator command."""

    id: str
    name: str
    status: JobStatus
    created_at: str


class JobStore:
    """Owns atomic Redis changes for commands, event payloads, and job status."""

    PREFIX = "ol:jobs"
    IDEMPOTENCY_PREFIX = "ol:idempotency"

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def enqueue(self, *, name: str, version: str, payload: dict, idempotency_key: str) -> Job:
        """Persist a command and first event atomically, returning the durable job."""
        idempotency_name = f"{self.IDEMPOTENCY_PREFIX}:{idempotency_key}"
        if existing := await self._redis.get(idempotency_name):
            return await self.get(existing.decode() if isinstance(existing, bytes) else existing)
        event = WorkflowEvent(name=name, version=version)
        job = Job(id=str(event.job_id), name=event.workflow_id, status="queued", created_at=datetime.now(UTC).isoformat())
        created = await self._redis.eval(
            """
            if redis.call('SET', KEYS[1], ARGV[1], 'NX') then
                redis.call('HSET', KEYS[2], 'name', ARGV[2], 'status', ARGV[3], 'created_at', ARGV[4])
                redis.call('SET', KEYS[3], ARGV[5])
                redis.call('XADD', KEYS[4], 'MAXLEN', '~', 5000,
                    'name', ARGV[6], 'version', ARGV[7], 'job_id', ARGV[8], 'status', ARGV[9])
                return 1
            end
            return 0
            """,
            4,
            idempotency_name,
            f"{self.PREFIX}:{job.id}",
            event.redis_key,
            EventStreams.WORKFLOWS,
            job.id,
            job.name,
            job.status,
            job.created_at,
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            event.name,
            event.version,
            str(event.job_id),
            event.status.value,
        )
        if not created:
            existing = await self._redis.get(idempotency_name)
            return await self.get(existing.decode() if isinstance(existing, bytes) else existing)
        return job

    async def get(self, job_id: str) -> Job:
        """Read a durable job record."""
        record = await self._redis.hgetall(f"{self.PREFIX}:{job_id}")
        decoded = {(key.decode() if isinstance(key, bytes) else key): (value.decode() if isinstance(value, bytes) else value) for key, value in record.items()}
        return Job(id=job_id, name=decoded["name"], status=decoded["status"], created_at=decoded["created_at"])

    async def list_recent(self, limit: int = 50) -> list[Job]:
        """Return the most recently created durable jobs for the Activity page."""
        keys = [key async for key in self._redis.scan_iter(match=f"{self.PREFIX}:*")]
        jobs = [await self.get(key.decode().rsplit(":", 1)[-1] if isinstance(key, bytes) else key.rsplit(":", 1)[-1]) for key in keys]
        return sorted(jobs, key=lambda job: job.created_at, reverse=True)[:limit]

    async def set_status(self, job_id: str, status: JobStatus) -> None:
        """Update the job state as a workflow event reaches a terminal result."""
        await self._redis.hset(f"{self.PREFIX}:{job_id}", "status", status)
