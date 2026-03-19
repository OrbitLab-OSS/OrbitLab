"""OrbitLab Workflow Models."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from orbitlab.data_types import WorkflowStepType
from orbitlab.manifest.ref import Ref
from orbitlab.manifest.serialization import SerializeEnum, SerializePath


class File(BaseModel):
    """Model for file push operations."""

    source: Annotated[Path, SerializePath]
    destination: Annotated[Path, SerializePath]


class Step(BaseModel):
    """Model for configuration steps in custom appliance creation."""

    type: Annotated[WorkflowStepType, SerializeEnum]
    name: str


class ScriptStep(Step):
    """A configuration step that executes a script during custom appliance creation."""

    type: Annotated[WorkflowStepType, SerializeEnum] = WorkflowStepType.SCRIPT
    script: str


class FileStep(Step):
    """A configuration step that handles pushing files during custom appliance creation."""

    type: Annotated[WorkflowStepType, SerializeEnum] = WorkflowStepType.FILES
    files: list[File]


class Network(BaseModel):
    """Model for network configuration settings."""

    sector: Ref
    subnet: str


class FileConfig(BaseModel):
    """File Configuration Model."""

    source: Path
    destination: Path | str = ""

    def configured(self) -> bool:
        """Check if the file push operation is properly configured."""
        return bool(self.destination)


class WorkflowStep(BaseModel):
    """Workflow Step Model."""

    type: WorkflowStepType | Literal[""] = Field(default="")
    name: str = Field(default="")
    script: str | None = Field(default=None)
    files: list[FileConfig] | None = Field(default=None)

    @property
    def valid(self) -> bool:
        """Check if the step has valid configuration."""
        files = [file.configured() for file in self.files] if self.files else [False]
        return any([self.script, *files])

    def validate(self) -> str:
        """Validate the step configuration and return any error messages."""
        if not self.name:
            return "Step name is not provided."
        if self.type == WorkflowStepType.FILES:
            if not self.files:
                return "No files uploaded for files step."
            for file in self.files:
                if not file.destination:
                    return f"File {file.source} as no specified destination."
        if self.type == WorkflowStepType.SCRIPT and not self.script:
            return "Script step has no configured shell script."
        return ""
