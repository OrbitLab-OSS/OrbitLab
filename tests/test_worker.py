"""Focused tests for Redis stream worker behavior."""

import asyncio

from orbitlab.constants import EventStreams
from orbitlab.worker.worker import Worker


class FakeRedis:
    """Minimal async Redis double for worker tests."""

    def __init__(
        self,
        *,
        pending_events: list[tuple[bytes, dict[bytes, bytes]]] | None = None,
        new_events: list[list] | None = None,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        self.pending_events = pending_events or []
        self.new_events = new_events or []
        self.stop_event = stop_event
        self.xack_calls: list[tuple[str, str, str]] = []
        self.xautoclaim_calls: list[tuple[str, str, str, int, str, int]] = []
        self.xreadgroup_calls: list[tuple[str, str, dict[str, str], int, int]] = []
        self.xgroup_create_calls: list[tuple[str, str, bool]] = []
        self.xadd_calls: list[tuple[str, dict]] = []

    async def xautoclaim(
        self,
        *,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        start_id: str,
        count: int,
    ) -> tuple[str, list[tuple[bytes, dict[bytes, bytes]]], list]:
        self.xautoclaim_calls.append((name, groupname, consumername, min_idle_time, start_id, count))
        events = self.pending_events
        self.pending_events = []
        return "0-0", events, []

    async def xreadgroup(
        self,
        *,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int,
        block: int,
    ) -> list[list]:
        self.xreadgroup_calls.append((groupname, consumername, streams, count, block))
        events = self.new_events
        self.new_events = []
        return events

    async def xgroup_create(self, *, name: str, groupname: str, mkstream: bool) -> None:
        self.xgroup_create_calls.append((name, groupname, mkstream))

    async def xack(self, stream: str, group: str, event_id: str) -> int:
        self.xack_calls.append((stream, group, event_id))
        if self.stop_event is not None:
            self.stop_event.set()
        return 1

    async def xadd(self, *, name: str, fields: dict, maxlen: int, approximate: bool) -> str:
        self.xadd_calls.append((name, fields))
        return "1-0"


def _build_worker(redis: FakeRedis) -> Worker:
    worker = Worker.__new__(Worker)
    worker.redis = redis
    worker._event = asyncio.Event()
    worker._workflows = set()
    worker.__dict__["node"] = "node-1"
    return worker


def test_read_stream_events_claims_pending_before_reading_new_messages() -> None:
    pending_event = (
        b"1-0",
        {
            b"name": b"instance.create",
            b"version": b"v1",
            b"job_id": b"00000000-0000-0000-0000-000000000000",
            b"status": b"in_progress",
        },
    )
    redis = FakeRedis(
        pending_events=[pending_event],
        new_events=[[EventStreams.WORKFLOWS, [(b"2-0", {b"name": b"should-not-be-read"})]]],
    )
    worker = _build_worker(redis)

    events = asyncio.run(worker._read_stream_events(stream=EventStreams.WORKFLOWS, consumer="node-1"))

    assert events == [
        (
            "1-0",
            {
                "name": "instance.create",
                "version": "v1",
                "job_id": "00000000-0000-0000-0000-000000000000",
                "status": "in_progress",
            },
        ),
    ]
    assert redis.xreadgroup_calls == []


def test_process_events_acks_consumed_messages() -> None:
    redis = FakeRedis(
        new_events=[
            [
                EventStreams.EVENTS,
                [
                    (
                        b"1-0",
                        {
                            b"event": b"instance.create",
                            b"version": b"v1",
                            b"payload": b"{\"id\": \"vm-123\"}",
                        },
                    ),
                ],
            ],
        ],
    )
    worker = _build_worker(redis)
    redis.stop_event = worker._event
    captured: list[tuple[str, str, dict]] = []

    async def create_workflow(*, name: str, version: str, payload: dict) -> str:
        captured.append((name, version, payload))
        return ""

    worker.create_workflow = create_workflow  # type: ignore[method-assign]

    asyncio.run(worker._process_events())

    assert captured == [("instance.create", "v1", {"id": "vm-123"})]
    assert redis.xgroup_create_calls == [(EventStreams.EVENTS, Worker.GROUP_NAME, True)]
    assert redis.xack_calls == [(EventStreams.EVENTS, Worker.GROUP_NAME, "1-0")]
