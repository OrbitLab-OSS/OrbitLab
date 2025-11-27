"""Schema definition for LXC template manifests in OrbitLab."""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, computed_field

from orbitlab.data_types import CustomApplianceStepType, ManifestKind
from orbitlab.manifest.schemas.base import BaseManifest, Metadata, Spec
from orbitlab.manifest.schemas.serialization import SerializeEnum, SerializePath


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
    created_on: datetime
    updated_on: datetime | None = None


class FilePush(BaseModel):
    source: Annotated[Path, SerializePath]
    destination: Annotated[Path | Literal[""], SerializePath, Field(default="")]

    def configured(self) -> bool:
        return bool(self.destination)


class Step(BaseModel):
    type: Annotated[CustomApplianceStepType, SerializeEnum]
    name: str = ""
    script: Annotated[str | None, Field(default=None)]
    files: Annotated[list[FilePush] | None, Field(default=None)]
    secrets: Annotated[list[str] | None, Field(default=None)]

    @property
    def valid(self) -> bool:
        files = [file.configured() for file in self.files] if self.files else [False]
        return any([self.script, *files, self.secrets])

    def validate(self) -> str:
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


class CustomApplianceSpec(Spec):
    base_appliance: str
    node: str
    storage: str
    certificate_authorities: list[str] | None
    steps: list[Step]


class CustomApplianceManifest(BaseManifest[CustomApplianceMetadata, CustomApplianceSpec]):
    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.CUSTOM_APPLIANCE
