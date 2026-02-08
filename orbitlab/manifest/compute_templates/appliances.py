"""Schema definition for LXC template manifests in OrbitLab."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Self

from pydantic import Field

from orbitlab.data_types import ManifestKind, WorkflowStatus
from orbitlab.manifest.base import BaseManifest, Metadata, Spec
from orbitlab.manifest.serialization import SerializeEnum
from orbitlab.services.vault.client import SecretVault

from .base import ComputeTemplateSpec, WorkflowUtilities

if TYPE_CHECKING:
    from orbitlab.clients.proxmox.compute_templates.models import ApplianceInfo, StoredAppliance
    from orbitlab.web.pages.compute.lxc.appliances.models import CreateCustomApplianceForm


class BaseApplianceMetadata(Metadata):
    """Metadata for an LXC appliance template."""

    description: str = ""
    download_date: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BaseApplianceSpec(Spec):
    """Specification for an LXC appliance template."""

    node: str
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
        node: str,
        storage: str,
        appliance: "ApplianceInfo",
    ) -> Self:
        """Create a BaseApplianceManifest from appliance info and save it."""
        manifest = cls(
            name=cls._generate_id("la"),
            metadata=BaseApplianceMetadata(
                description=appliance.description,
            ),
            spec=BaseApplianceSpec(
                node=node,
                template=appliance.template,
                storage=storage,
            ),
        )
        manifest.save()
        return manifest

    @classmethod
    def create_from_stored_appliance(cls, node: str, appliance: "StoredAppliance") -> Self:
        """Create a BaseApplianceManifest from a stored appliance and save it."""
        return cls(
            name=cls._generate_id("la"),
            metadata=BaseApplianceMetadata(
                description="",
            ),
            spec=BaseApplianceSpec(
                node=node,
                template=appliance.template,
                storage=appliance.storage,
            ),
        )


class CustomApplianceMetadata(Metadata):
    """Metadata for a custom appliance template."""

    name: str
    created_on: datetime = datetime.now(UTC)
    last_update: datetime | None = None
    last_execution: datetime | None = None
    status: Annotated[WorkflowStatus, SerializeEnum] = Field(
        default=WorkflowStatus.PENDING,
    )
    logs: list[str] = Field(default_factory=list)


class CustomApplianceSpec(ComputeTemplateSpec):
    """Specification for a custom appliance template."""

    base_appliance: str
    node: str
    storage: str
    rootfs: str
    memory: int
    swap: int
    certificate_authorities: list[str] = Field(default_factory=list)
    sector: str


class CustomApplianceManifest(BaseManifest[CustomApplianceMetadata, CustomApplianceSpec], WorkflowUtilities):
    """Custom LXC Appliance Manifest."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.CUSTOM_APPLIANCE

    @property
    def ostemplate(self) -> str:
        """Return the Proxmox volume ID string for this custom appliance."""
        return f"{self.spec.storage}:vztmpl/{self.name}.tar.gz"

    def workflow_params(self, vmid: int) -> dict[str, str | int]:
        """Generate the parameters required to create a Proxmox LXC container from this manifest."""
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
            "net0": f"name=eth0,bridge={self.spec.sector},ip=dhcp",
        }

    def update(self, form_data: "CreateCustomApplianceForm") -> None:
        """Update the manifest with data from the CreateCustomApplianceForm."""
        self.metadata.name = form_data.name
        self.spec = CustomApplianceSpec(
            base_appliance=form_data.base_appliance,
            node=form_data.node,
            storage=form_data.storage,
            rootfs=form_data.rootfs,
            memory=form_data.memory,
            swap=form_data.swap,
            sector=form_data.sector,
        )
        self.spec.add_steps(form_data.workflow_steps)
        self.save()

    @classmethod
    def create(cls, form_data: "CreateCustomApplianceForm") -> Self:
        """Create a manifest from the CreateCustomAppliance form data."""
        manifest = cls(
            name=cls._generate_id(prefix="lai"),
            metadata=CustomApplianceMetadata(name=form_data.name),
            spec=CustomApplianceSpec(
                base_appliance=form_data.base_appliance,
                node=form_data.node,
                storage=form_data.storage,
                rootfs=form_data.rootfs,
                memory=form_data.memory,
                swap=form_data.swap,
                sector=form_data.sector,
            ),
        )
        manifest.spec.add_steps(form_data.workflow_steps)
        manifest.save()
        return manifest
