"""Workflow work/commit chain tests that do not require Redis or Proxmox."""

from orbitlab.data_types import EventStatus
from orbitlab.worker.events import WorkflowEvent
from orbitlab.worker.workflows.base import WorkflowPayload


def test_legacy_state_payload_migrates_to_a_work_phase() -> None:
    payload = WorkflowPayload.model_validate({"id": "i-123", "state": "configuring"})

    assert payload.step == "configure"
    assert payload.phase == "work"
    assert payload.result is None


def test_short_circuit_terminal_payload_preserves_its_result() -> None:
    payload = WorkflowPayload.model_validate({"id": "i-123", "state": "succeeded"})

    assert payload.step == "succeeded"
    assert payload.phase == "work"
    assert payload.result == EventStatus.SUCCEEDED


def test_workflow_events_expose_step_and_phase_for_stream_inspection() -> None:
    event = WorkflowEvent(name="instance.create", version="v1", step="provision", phase="commit")

    assert event.step == "provision"
    assert event.phase == "commit"
