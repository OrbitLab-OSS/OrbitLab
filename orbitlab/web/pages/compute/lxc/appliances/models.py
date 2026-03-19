"""OrbitLab LXC Models."""

from pydantic import BaseModel, Field

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
    workflow_steps: list[WorkflowStep]
    sector: str


class ApplianceItemDownload(BaseModel):
    """Model for appliance item download information."""

    node: str = ""
    storage: str = ""
    available_storage: list[str] = Field(default_factory=list)
    downloading: bool = False
