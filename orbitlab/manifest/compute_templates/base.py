"""OrbitLab's Base Custom Compute Templates."""

from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Protocol

from pydantic import Field

from orbitlab.data_types import WorkflowStatus, WorkflowStepType
from orbitlab.manifest.base import Spec
from orbitlab.services.vault.client import SecretVault

from .workflow_models import File, FileStep, ScriptStep, WorkflowStep


class ComputeTemplateSpec(Spec):
    """Base specification for custom compute templates."""

    steps: list[FileStep | ScriptStep] = Field(default_factory=list)

    def add_steps(self, workflow_steps: list[WorkflowStep]) -> None:
        """Add workflow steps during creation."""
        for step in workflow_steps:
            if step.type == WorkflowStepType.FILES:
                self.steps.append(
                    FileStep(
                        name=step.name,
                        files=[
                            File(
                                source=file.source,
                                destination=file.destination
                                if isinstance(file.destination, Path)
                                else Path(file.destination),
                            )
                            for file in step.files or []
                        ],
                    ),
                )
            if step.type == WorkflowStepType.SCRIPT:
                self.steps.append(
                    ScriptStep(
                        name=step.name,
                        script=step.script or "",
                    ),
                )


class Metadata(Protocol):
    """Protocol for workflow metadata."""

    status: WorkflowStatus
    last_execution: datetime
    logs: list[str]


class WorkflowUtilities:
    """Workflow execution utilities for custom compute templates."""

    metadata: ClassVar[Metadata]

    def set_workflow_status(self, status: WorkflowStatus) -> None:
        """Set the workflow status of the custom compute template and update dates, if necessary."""
        self.metadata.status = status
        if status == WorkflowStatus.PENDING:
            self.metadata.last_execution = datetime.now(UTC)
        self.save()

    def workflow_log(self, message: str, *, truncate: bool = False) -> None:
        """Append a message to the workflow log, optionally truncating existing logs."""
        if truncate:
            self.metadata.logs = []
        self.metadata.logs.append(message)
        self.save()

    def generate_random_password(self) -> str:
        """Generate and return a random password using the SecretVault service."""
        return SecretVault.generate_random_password()

    def save(self) -> None:
        """Implementation overwritten by subclassed BaseManifest."""
