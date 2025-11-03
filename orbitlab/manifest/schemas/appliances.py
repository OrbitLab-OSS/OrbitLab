"""Schema definition for LXC template manifests in OrbitLab."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field

from orbitlab.data_types import CustomApplianceStepType, ManifestKind
from orbitlab.manifest.schemas.base import BaseManifest, Metadata, Spec
from orbitlab.manifest.schemas.serialization import SerializeEnum


class BaseApplianceMetadata(Metadata):
    """Metadata for an LXC appliance template.

    Attributes:
        turnkey: Whether this is a TurnKey Linux template.
        section: The category or section of the appliance.
        info: Description or information about the appliance.
        checksum: The checksum for verifying the template integrity.
        url: The URL to download the template.
    """
    turnkey: bool
    section: str
    info: str
    checksum: str
    url: str


class BaseApplianceSpec(Spec):
    """Specification for an LXC appliance template.

    Args:
        node: The Proxmox node where the template is stored.
        template: The template identifier.
        storage: The storage location for the template.
        architecture: The CPU architecture of the template.
        version: The version of the template.
        os_type: The operating system type.
    """
    node: str
    template: str
    storage: str
    architecture: str
    version: str
    os_type: str


class BaseApplianceManifest(BaseManifest[BaseApplianceMetadata, BaseApplianceSpec]):
    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.BASE_APPLIANCE



class CustomApplianceMetadata(Metadata):
    name: str
    base_appliance: str
    created_on: datetime
    updated_on: datetime | None = None


class Step(BaseModel):
    type: CustomApplianceStepType
    script: Annotated[str | None, Field(default=None)]
    files: Annotated[list[Path] | None, Field(default=None)]


class CustomApplianceSpec(Spec):
    node: str
    storage: str
    steps: list[Step]


class CustomApplianceManifest(BaseManifest[CustomApplianceMetadata, CustomApplianceSpec]):
    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.CUSTOM_APPLIANCE
