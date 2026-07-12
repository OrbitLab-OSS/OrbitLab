"""OrbitLab Workflow Models."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from orbitlab.data_types import WorkflowStepType
from orbitlab.redis.models import File, FileStep, ScriptStep


class FileConfig(BaseModel):
    """File Configuration Model."""

    source: Path
    destination: Path | str = ""

    def configured(self) -> bool:
        """Check if the file push operation is properly configured."""
        return bool(self.destination)

    def to_file(self) -> File:
        if not isinstance(self.destination, Path):
            self.destination = Path(self.destination)
        return File(source=self.source, destination=self.destination)


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

    def to_step(self) -> ScriptStep | FileStep:
        if self.type == WorkflowStepType.FILES and self.files:
            return FileStep(name=self.name, files=[config.to_file() for config in self.files])
        if self.type == WorkflowStepType.SCRIPT and self.script:
            return ScriptStep(name=self.name, script=self.script)
        raise RuntimeError
