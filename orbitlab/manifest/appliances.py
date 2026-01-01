"""Schema definition for LXC template manifests in OrbitLab."""

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import BaseModel, Field

from orbitlab.clients.proxmox.appliances.models import ApplianceInfo, StoredAppliance
from orbitlab.data_types import CustomApplianceStepType, CustomApplianceWorkflowStatus, ManifestKind
from orbitlab.manifest.ref import Ref
from orbitlab.manifest.sector import SectorManifest
from orbitlab.services.vault.client import SecretVault

from .base import BaseManifest, Metadata, Spec
from .serialization import SerializeEnum, SerializePath

if TYPE_CHECKING:
    from orbitlab.web.pages.compute.lxc.appliances.models import CreateCustomApplianceForm


class BaseApplianceMetadata(Metadata):
    """Metadata for an LXC appliance template."""

    description: str = ""
    download_date: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BaseApplianceSpec(Spec):
    """Specification for an LXC appliance template."""

    node: Ref
    template: str
    storage: str


class BaseApplianceManifest(BaseManifest[BaseApplianceMetadata, BaseApplianceSpec]):
    """Base LXC Appliance Manifest."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.BASE_APPLIANCE

    @property
    def ostemplate(self) -> str:
        """Return the Proxmox ostemplate string for this appliance."""
        return f"{self.spec.storage}:vztmpl/{self.spec.template}"

    @classmethod
    def create_from_appliance_info(
        cls,
        node_ref: Ref,
        storage: str,
        appliance: ApplianceInfo,
    ) -> "BaseApplianceManifest":
        """Create a BaseApplianceManifest from appliance info and save it."""
        manifest = cls.model_validate(
            {
                "name": appliance.template,
                "metadata": {
                    "description": appliance.description,
                },
                "spec": {
                    "node": node_ref,
                    "template": appliance.template,
                    "storage": storage,
                },
            },
        )
        manifest.save()
        return manifest

    @classmethod
    def create_from_stored_appliance(cls, node_ref: Ref, appliance: StoredAppliance) -> Self:
        """Create a BaseApplianceManifest from a stored appliance and save it."""
        return cls.model_validate(
            {
                "name": appliance.template,
                "metadata": {
                    "description": "",
                },
                "spec": {
                    "node": node_ref,
                    "template": appliance.template,
                    "storage": appliance.storage,
                },
            },
        )


class CustomApplianceMetadata(Metadata):
    """Metadata for a custom appliance template."""

    created_on: datetime = datetime.now(UTC)
    last_update: datetime | None = None
    last_execution: datetime | None = None
    status: Annotated[CustomApplianceWorkflowStatus, SerializeEnum]
    logs: list[str] = Field(default_factory=list)


class File(BaseModel):
    """Model for file push operations."""

    source: Annotated[Path, SerializePath]
    destination: Annotated[Path, SerializePath]


class Step(BaseModel):
    """Model for configuration steps in custom appliance creation."""

    type: Annotated[CustomApplianceStepType, SerializeEnum]
    name: str


class ScriptStep(Step):
    """A configuration step that executes a script during custom appliance creation."""

    type: Literal[CustomApplianceStepType.SCRIPT] = CustomApplianceStepType.SCRIPT
    script: str


class FileStep(Step):
    """A configuration step that handles pushing files during custom appliance creation."""

    type: Literal[CustomApplianceStepType.FILES] = CustomApplianceStepType.FILES
    files: list[File]


class Network(BaseModel):
    """Model for network configuration settings."""

    sector: Ref
    subnet: str


class CustomApplianceSpec(Spec):
    """Specification for a custom appliance template."""

    base_appliance: str
    node: str
    storage: str
    rootfs: str
    memory: int
    swap: int
    certificate_authorities: list[str] = Field(default_factory=list)
    steps: list[FileStep | ScriptStep]
    networks: list[Network]


class CustomApplianceManifest(BaseManifest[CustomApplianceMetadata, CustomApplianceSpec]):
    """Custom LXC Appliance Manifest."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.CUSTOM_APPLIANCE

    @property
    def ostemplate(self) -> str:
        """Return the Proxmox volume ID string for this custom appliance."""
        return f"{self.spec.storage}:vztmpl/{self.name}.tar.gz"

    def set_workflow_status(self, status: CustomApplianceWorkflowStatus) -> None:
        """Set the workflow status of the custom appliance and update dates, if necessary."""
        self.metadata.status = status
        if status == CustomApplianceWorkflowStatus.PENDING:
            self.metadata.last_execution = datetime.now(UTC)
        self.save()

    def workflow_log(self, message: str, *, truncate: bool = False) -> None:
        """Append a message to the workflow log, optionally truncating existing logs."""
        if truncate:
            self.metadata.logs = []
        self.metadata.logs.append(message)
        self.save()

    def workflow_params(self, vmid: int) -> dict[str, str | int]:
        """Generate the parameters required to create a Proxmox LXC container from this manifest."""
        networks: dict[str, str] = {}
        for index, network in enumerate(self.spec.networks):
            sector = SectorManifest.load(name=network.sector.name)
            ipam = sector.get_ipam()
            ip = ipam.assign_ip(subnet_name=network.subnet, vmid=vmid)
            networks[f"net{index}"] = (
                f"name=eth{index},"
                f"bridge={network.sector.name},"
                f"ip={ip.with_prefixlen},"
                f"gw={sector.get_subnet(name=network.subnet).default_gateway.ip}"
            )
        base = BaseApplianceManifest.load(name=self.spec.base_appliance)
        return {
            "ssh-public-keys": "",
            "features": "nesting=1",
            "cores": "2",
            "unprivileged": "1",
            "onboot": "0",
            "vmid": vmid,
            "memory": f"{self.spec.memory * 1024}",
            "swap": f"{self.spec.swap * 1024}",
            "ostemplate": base.ostemplate,
            "hostname": f"oca-wf-{vmid}",
            "rootfs": f"{self.spec.rootfs}:8",
            "password": SecretVault.generate_random_password(),
            **networks,
        }

    @classmethod
    def create(cls, form: "CreateCustomApplianceForm") -> Self:
        """Create a manifest from the CreateCustomAppliance form data."""
        manifest = cls.model_validate(
            {
                "name": form.name,
                "metadata": {},
                "spec": {
                    "base_appliance": form.base_appliance,
                    "node": form.node,
                    "storage": form.storage,
                    "memory": form.memory,
                    "swap": form.swap,
                    "certificate_authorities": form.certificate_authorities,
                    "steps": form.workflow_steps,
                    "networks": [
                        {
                            "sector": SectorManifest.load(name=config.sector).to_ref(),
                            "subnet": config.subnet,
                        }
                        for config in form.networks
                    ],
                },
            },
        )
        manifest.save()
        return manifest
