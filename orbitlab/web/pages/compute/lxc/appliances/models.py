"""OrbitLab LXC Models."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from orbitlab.data_types import CustomApplianceStepType


class NetworkConfig(BaseModel):
    """Network configuration for an LXC container."""

    sector: str = ""
    subnet: str = ""
    available_subnets: dict[str, str] = Field(default_factory=dict)


class FileConfig(BaseModel):
    """File Configuration Model."""

    source: Path
    destination: Path | str = ""

    def configured(self) -> bool:
        """Check if the file push operation is properly configured."""
        return bool(self.destination)


class WorkflowStep(BaseModel):
    """Workflow Step Model."""

    type: CustomApplianceStepType | Literal[""] = Field(default="")
    name: str = Field(default="")
    script: str | None = Field(default=None)
    files: list[FileConfig] | None = Field(default=None)
    secrets: list[str] | None = Field(default=None)

    @property
    def valid(self) -> bool:
        """Check if the step has valid configuration."""
        files = [file.configured() for file in self.files] if self.files else [False]
        return any([self.script, *files, self.secrets])

    def validate(self) -> str:
        """Validate the step configuration and return any error messages."""
        if not self.name:
            return "Step name is not provided."
        if self.type == CustomApplianceStepType.FILES:
            if not self.files:
                return "No files uploaded for files step."
            for file in self.files:
                if not file.destination:
                    return f"File {file.source} as no specified destination."
        if self.type == CustomApplianceStepType.SCRIPT and not self.script:
            return "Script step has no configured shell script."
        return ""


class CreateCustomApplianceForm(BaseModel):
    """Form model for creating custom appliances."""

    name: str
    base_appliance: str
    node: str
    storage: str
    memory: int
    swap: int
    certificate_authorities: list[str] | None
    workflow_steps: list[WorkflowStep]
    networks: list[NetworkConfig]

    @field_validator("certificate_authorities", mode="plain")
    @classmethod
    def validate_certs(cls, value: str) -> list[str] | None:
        """Validate and parse certificate authorities from JSON string."""
        if value:
            return json.loads(value)
        return None


class ApplianceItemDownload(BaseModel):
    """Model for appliance item download information."""

    node: str = ""
    storage: str = ""
    available_storage: list[str] = Field(default_factory=list)
    downloading: bool = False
