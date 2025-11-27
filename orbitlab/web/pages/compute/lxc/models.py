"""OrbitLab LXC Models."""

import json
from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator

from orbitlab.manifest.schemas.appliances import (
    CustomApplianceManifest,
    CustomApplianceMetadata,
    CustomApplianceSpec,
    Step,
)


class CreateCustomApplianceForm(BaseModel):
    """Form model for creating custom appliances.

    This model validates and structures the form data required to create
    a custom appliance from a base appliance, including configuration
    settings and workflow steps.
    """
    name: str
    base_appliance: str
    node: str
    storage: str
    certificate_authorities: list[str] | None
    workflow_steps: list[Step]

    @field_validator("certificate_authorities", mode="plain")
    @classmethod
    def validate_certs(cls, value: str) -> list[str] | None:
        """Validate and parse certificate authorities from JSON string."""
        if value:
            return json.loads(value)
        return None

    def generate_manifest(self) -> CustomApplianceManifest:
        """Generate a `CustomApplianceManifest` from the form data."""
        return CustomApplianceManifest(
            name=self.name,
            metadata=CustomApplianceMetadata(
                name=self.name,
                created_on=datetime.now(UTC),
            ),
            spec=CustomApplianceSpec(
                base_appliance=self.base_appliance,
                node=self.node,
                storage=self.storage,
                certificate_authorities=self.certificate_authorities,
                steps=self.workflow_steps,
            ),
        )


class ApplianceItemDownload(BaseModel):
    """Model for appliance item download information.

    This model tracks the download status and storage configuration
    for appliance items.
    """
    node: str = ""
    storage: str = ""
    available_storage: list[str] = Field(default_factory=list)
    downloading: bool = False
