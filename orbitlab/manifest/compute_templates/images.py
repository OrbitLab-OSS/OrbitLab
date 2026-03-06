"""Schema definition for VM image manifests in OrbitLab."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Self

from pydantic import Field

from orbitlab.data_types import ManifestKind
from orbitlab.manifest.base import BaseManifest, Metadata, Spec
from orbitlab.manifest.sector import SectorManifest
from orbitlab.manifest.serialization import SerializeEnum

from .base import ComputeTemplateSpec, WorkflowUtilities

if TYPE_CHECKING:
    from orbitlab.proxmox.compute.models import VendoredImage
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
    volume_id: str = ""
    checksum_algorithm: str
    checksum: str


class BaseImageManifest(BaseManifest[BaseImageMetadata, BaseImageSpec]):
    """Manifest schema for a VM image in OrbitLab."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.BASE_IMAGE

    def update(self, volume_id: str, image: "VendoredImage") -> None:
        """Update the manifest metadata and spec fields using the provided asset."""
        self.metadata.build_date = image.build_date
        self.metadata.download_url = image.browser_download_url
        self.spec.filename = image.filename
        self.spec.volume_id = volume_id
        self.spec.checksum_algorithm, self.spec.checksum = image.digest.split(":")
        self.save()

    def download_params(self) -> dict[str, str]:
        """Return the download parameters for this image."""
        return {
            "content": "import",
            "url": self.metadata.download_url,
            "filename": self.spec.filename,
            "checksum": self.spec.checksum,
            "checksum-algorithm": self.spec.checksum_algorithm,
        }

    @classmethod
    def create(cls, storage: str, node: str, image: "VendoredImage") -> Self:
        """Create and save a new BaseImageManifest instance from the given storage, node, and asset."""
        checksum_algorithm, checksum = image.digest.split(":")
        manifest = cls(
            name=cls._generate_id("vmi"),
            metadata=BaseImageMetadata(
                os=image.formatted_name,
                build_date=image.build_date,
                download_url=image.browser_download_url,
            ),
            spec=BaseImageSpec(
                node=node,
                filename=image.filename,
                storage=storage,
                checksum=checksum,
                checksum_algorithm=checksum_algorithm,
            ),
        )
        manifest.save()
        return manifest


class CustomImageMetadata(Metadata):
    """Metadata for a custom VM image."""

    name: str
    created_on: datetime = datetime.now(UTC)
    last_update: datetime | None = None
    last_execution: datetime | None = None


class CustomImageSpec(ComputeTemplateSpec):
    """Specification for a custom VM image in OrbitLab."""

    base_image: str
    node: str
    volume_id: str = ""
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
            "scsi0": f"{self.spec.disk_storage}:0,import-from={base_image.spec.volume_id}",
            "ide0": f"{self.spec.disk_storage}:cloudinit",
            "citype": "nocloud",
            "ciuser": "root",
            "ciupgrade": "1",
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
