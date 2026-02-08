"""Schema definition for VM image manifests in OrbitLab."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Self

from pydantic import Field

from orbitlab.data_types import ManifestKind, WorkflowStatus
from orbitlab.manifest.base import BaseManifest, Metadata, Spec
from orbitlab.manifest.sector import SectorManifest
from orbitlab.manifest.serialization import SerializeEnum

from .base import ComputeTemplateSpec, WorkflowUtilities

if TYPE_CHECKING:
    from orbitlab.clients.proxmox.compute.models import Asset
    from orbitlab.web.pages.compute.vm.images.models import CreateCustomImageForm


class BaseImageMetadata(Metadata):
    """Metadata for a VM image in OrbitLab."""

    os: str
    build_date: str
    download_url: str
    download_date: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BaseImageSpec(Spec):
    """Specification for a VM image in OrbitLab."""

    node: str
    filename: str
    storage: str


class BaseImageManifest(BaseManifest[BaseImageMetadata, BaseImageSpec]):
    """Manifest schema for a VM image in OrbitLab."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.BASE_IMAGE

    @property
    def volume_id(self) -> str:
        """Return the volume ID for this image manifest."""
        return f"{self.spec.storage}:import/{self.spec.filename}"

    def update(self, asset: "Asset") -> None:
        """Update the manifest metadata and spec fields using the provided asset."""
        self.metadata.build_date = asset.build_date
        self.metadata.download_url = asset.browser_download_url
        self.spec.filename = asset.name
        self.save()

    @classmethod
    def create(cls, storage: str, node: str, asset: "Asset") -> None:
        """Create and save a new BaseImageManifest instance from the given storage, node, and asset."""
        manifest = cls(
            name=asset.name,
            metadata=BaseImageMetadata(
                os=asset.formatted_name,
                build_date=asset.build_date,
                download_url=asset.browser_download_url,
            ),
            spec=BaseImageSpec(
                node=node,
                filename=asset.name,
                storage=storage,
            ),
        )
        manifest.save()


class CustomImageMetadata(Metadata):
    """Metadata for a custom VM image."""

    name: str
    created_on: datetime = datetime.now(UTC)
    last_update: datetime | None = None
    last_execution: datetime | None = None
    status: Annotated[WorkflowStatus, SerializeEnum] = Field(default=WorkflowStatus.PENDING)
    logs: list[str] = Field(default_factory=list)


class CustomImageSpec(ComputeTemplateSpec):
    """Specification for a custom VM image in OrbitLab."""

    base_image: str
    node: str
    disk_storage: str
    disk_size: int
    image_storage: str
    memory: int
    cores: int
    certificate_authorities: list[str] = Field(default_factory=list)
    sector: str


class CustomImageManifest(BaseManifest[CustomImageMetadata, CustomImageSpec], WorkflowUtilities):
    """Custom VM Image Manifest."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.CUSTOM_IMAGE

    @property
    def volume_id(self) -> str:
        """Return the volume ID for this image manifest."""
        return f"{self.spec.image_storage}:import/{self.name}.qcow2"

    def workflow_params(self, vmid: int) -> dict[str, str | int]:
        """Generate workflow parameters for provisioning a VM from which to build a custom image."""
        sector = SectorManifest.load(name=self.spec.sector)
        base_image = BaseImageManifest.load(name=self.spec.base_image)
        return {
            "vmid": vmid,
            "name": self._generate_id("wfvm"),
            "cores": self.spec.cores,
            "sockets": "1",
            "memory": self.spec.memory * 1024,
            "cpu": "x86-64-v2-AES",
            "numa": 0,
            "agent": "enabled=1",
            "serial0": "socket",
            "scsi0": f"{self.spec.disk_storage}:0,import-from={base_image.volume_id}",
            "ide0": f"{self.spec.disk_storage}:cloudinit",
            "citype": "nocloud",
            "ciuser": "root",
            "ciupgrade": "0",
            "cipassword": self.generate_random_password(),
            "net0": f"virtio,bridge={sector.name}",
            "ipconfig0": "ip=dhcp",
            "searchdomain": "sector.internal",
            "nameserver": f"{sector.dns_address.ip}",
            "scsihw": "virtio-scsi-single",
            "ostype": "l26",
            "onboot": "0",
            "boot": "order=scsi0",
        }

    def update(self, form_data: "CreateCustomImageForm") -> None:
        """Update the manifest metadata and spec fields using the provided form data."""
        self.metadata.name = form_data.name
        self.spec = CustomImageSpec(
            base_image=form_data.base_image,
            node=form_data.node,
            disk_storage=form_data.disk_store,
            disk_size=form_data.disk_size,
            image_storage=form_data.image_store,
            memory=form_data.memory,
            cores=form_data.cores,
            sector=form_data.sector,
        )
        self.spec.add_steps(form_data.workflow_steps)
        self.save()

    @classmethod
    def create(cls, form_data: "CreateCustomImageForm") -> Self:
        """Create and save a new CustomImageManifest instance from the provided form data."""
        manifest = cls(
            name=cls._generate_id("vmi"),
            metadata=CustomImageMetadata(name=form_data.name),
            spec=CustomImageSpec(
                base_image=form_data.base_image,
                node=form_data.node,
                disk_storage=form_data.disk_store,
                disk_size=form_data.disk_size,
                image_storage=form_data.image_store,
                memory=form_data.memory,
                cores=form_data.cores,
                sector=form_data.sector,
            ),
        )
        manifest.spec.add_steps(form_data.workflow_steps)
        manifest.save()
        return manifest
