"""VM Image Management Models."""

from pydantic import BaseModel

from orbitlab.manifest.compute_templates.workflow_models import WorkflowStep


class CreateCustomImageForm(BaseModel):
    """Form model for creating custom VM images."""

    node: str
    base_image: str
    name: str
    image_store: str
    disk_store: str
    sector: str
    memory: int
    cores: int
    disk_size: int
    workflow_steps: list[WorkflowStep]
