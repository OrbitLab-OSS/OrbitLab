"""Schema definition for LXC template manifests in OrbitLab."""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from orbitlab.clients.proxmox.appliances.models import ApplianceInfo, StoredAppliance
from orbitlab.data_types import CustomApplianceStepType, ManifestKind
from orbitlab.manifest.ref import Ref

from .base import BaseManifest, Metadata, Spec
from .serialization import SerializeEnum, SerializePath


class BaseApplianceMetadata(Metadata):
    """Metadata for an LXC appliance template."""

    description: str = ""


class BaseApplianceSpec(Spec):
    """Specification for an LXC appliance template."""

    node: Ref
    template: str
    storage: str


class BaseApplianceManifest(BaseManifest[BaseApplianceMetadata, BaseApplianceSpec]):
    """Base LXC Appliance Manifest."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.BASE_APPLIANCE

    @classmethod
    def create_from_appliance_info(cls, node_ref: Ref, storage: str, appliance: ApplianceInfo) -> None:
        """Create a BaseApplianceManifest from appliance info and save it."""
        cls.model_validate({
            "name": appliance.template,
            "metadata": {
                "description": appliance.description,
            },
            "spec": {
                "node": node_ref,
                "template": appliance.template,
                "storage": storage,
            },
        }).save()

    @classmethod
    def create_from_stored_appliance(cls, node_ref: Ref, appliance: StoredAppliance) -> "BaseApplianceManifest":
        """Create a BaseApplianceManifest from a stored appliance and save it."""
        return cls.model_validate({
            "name": appliance.template,
            "metadata": {
                "description": "",
            },
            "spec": {
                "node": node_ref,
                "template": appliance.template,
                "storage": appliance.storage,
            },
        })


class CustomApplianceMetadata(Metadata):
    """Metadata for a custom appliance template."""

    name: str
    created_on: datetime
    last_update: datetime | None = None
    last_execution: datetime | None = None


class FilePush(BaseModel):
    """Model for file push operations.

    Represents a file that needs to be pushed from a source location
    to a destination location during appliance configuration.
    """
    source: Annotated[Path, SerializePath]
    destination: Annotated[Path | Literal[""], SerializePath] = ""

    def configured(self) -> bool:
        """Check if the file push operation is properly configured."""
        return bool(self.destination)


class Step(BaseModel):
    """Model for configuration steps in custom appliance creation.

    Represents a single step in the appliance configuration process,
    which can include script execution, file operations, or secret management.
    """
    type: Annotated[CustomApplianceStepType | Literal[""], SerializeEnum] = Field(default="")
    name: str = Field(default="")
    script: str | None = Field(default=None)
    files: list[FilePush] | None = Field(default=None)
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


class Network(BaseModel):
    """Model for network configuration settings.

    This model defines network settings including bridge configuration
    and IP address configuration types for both IPv4 and IPv6.
    """
    name: str = ""
    subnet: str = ""


class CustomApplianceSpec(Spec):
    """Specification for a custom appliance template.

    Defines the configuration parameters for creating a custom LXC appliance,
    including base appliance, resources, networking, and configuration steps.
    """
    base_appliance: str
    node: str
    storage: str
    memory: int
    swap: int
    certificate_authorities: list[str] | None
    steps: list[Step]
    networks: list[Network]


class CustomApplianceManifest(BaseManifest[CustomApplianceMetadata, CustomApplianceSpec]):
    """Custom LXC Appliance Manifest.

    Represents a manifest for creating custom LXC appliances with 
    specific configurations, steps, and network settings.
    """
    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.CUSTOM_APPLIANCE

    def to_create_params(self) -> dict[str, str | int]:
        """Convert the manifest specification to Proxmox LXC creation parameters."""
        #TODO: Finish after IPAM integration
        return {
            "hostname": f"oca-{self.name}",
            "ostemplate": self.spec.base_appliance,
            "rootfs": f"{self.spec.storage}:8",
            "memory": self.spec.memory,
            "swap": self.spec.swap,
        }
