"""OrbitLab LXC Models."""

import json

from pydantic import BaseModel, Field, field_validator

from orbitlab.manifest.compute_templates.workflow_models import WorkflowStep


class CreateCustomApplianceForm(BaseModel):
    """Form model for creating custom appliances."""

    name: str
    base_appliance: str
    node: str
    storage: str
    rootfs: str
    memory: int
    swap: int
    certificate_authorities: list[str] | None
    workflow_steps: list[WorkflowStep]
    sector: str

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
