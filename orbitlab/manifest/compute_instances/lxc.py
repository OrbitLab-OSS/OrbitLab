"""Schema definitions for LXC container manifests in OrbitLab."""

from ipaddress import IPv4Interface
from typing import Annotated, Self

from orbitlab.data_types import ComputeState, ComputeStatus, ManifestKind
from orbitlab.manifest.base import BaseManifest, Metadata, Spec
from orbitlab.manifest.compute_templates import CustomApplianceManifest
from orbitlab.manifest.ref import Ref
from orbitlab.manifest.secrets import SecretManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.manifest.serialization import SerializeEnum, SerializeIP
from orbitlab.services.discovery import BaseApplianceManifest
from orbitlab.web.pages.compute.lxc.instances.models import CreateLXCForm


class LXCMetadata(Metadata):
    """Metadata schema for LXC containers."""

    sector_id: str
    sector_name: str
    hostname: str
    on_boot: bool = True
    status: Annotated[ComputeState, SerializeEnum] = ComputeState.STARTING
    node: str
    vmid: int | None = None
    address: Annotated[IPv4Interface, SerializeIP] | None = None


class LXCSpec(Spec):
    """Specification schema for LXC containers."""

    os_template: str
    disk_storage: str
    disk_size: int
    sector: str
    password: Ref | None = None
    ssh_public_key: Ref | str = ""
    memory: int
    swap: int
    cores: int


class LXCManifest(BaseManifest[LXCMetadata, LXCSpec]):
    """Manifest schema for LXC containers in OrbitLab."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.LXC

    def create_lxc_params(self, vmid: int) -> dict[str, int | str]:
        """Generate the parameters required to create an LXc in Proxmox."""
        self.metadata.vmid = vmid
        dns_address = SectorManifest.load(name=self.spec.sector).dns_address
        self.save()
        return {
            "features": "nesting=1",
            "ostemplate": self.spec.os_template,
            "hostname": self.metadata.hostname,
            "cores": self.spec.cores,
            "memory": self.spec.memory * 1024,
            "swap": self.spec.memory * 1024,
            "net0": f"name=eth0,bridge={self.spec.sector},ip=dhcp",
            "rootfs": f"{self.spec.disk_storage}:{self.spec.disk_size}",
            "unprivileged": "1",
            "vmid": vmid,
            "ssh-public-keys": "",
            "password": self.get_password(),
            "searchdomain": "sector.internal",
            "nameserver": f"{dns_address.ip}",
            "onboot": "1" if self.metadata.on_boot else "0",
        }

    def get_password(self) -> str:
        """Retrieve the current password value from the referenced secret manifest."""
        if self.spec.password:
            return SecretManifest.load(name=self.spec.password.name).get_current_value()
        return ""

    def set_status(self, status: ComputeStatus, *, completed: bool = False) -> None:
        """Update the status in the manifest based on the provided ComputeStatus."""
        match status:
            case ComputeStatus.START:
                self.metadata.status = ComputeState.RUNNING if completed else ComputeState.STARTING
            case ComputeStatus.REBOOT:
                self.metadata.status = ComputeState.RUNNING if completed else ComputeState.RESTARTING
            case ComputeStatus.STOP:
                self.metadata.status = ComputeState.STOPPED if completed else ComputeState.STOPPING
            case ComputeStatus.SHUTDOWN:
                self.metadata.status = ComputeState.STOPPED if completed else ComputeState.STOPPING
            case ComputeStatus.TERMINATE:
                self.metadata.status = ComputeState.TERMINATING
        self.save()

    def delete(self) -> None:
        """Delete the VM manifest and remove its associated secret."""
        if self.spec.password:
            SecretManifest.load(name=self.spec.password.name).delete()
        super().delete()

    @classmethod
    def create(cls, form: CreateLXCForm) -> Self:
        """Create a new LXCManifest instance from the provided form data."""
        if form.appliance in BaseApplianceManifest.get_existing():
            appliance = BaseApplianceManifest.load(name=form.appliance)
        else:
            appliance = CustomApplianceManifest.load(name=form.appliance)
        sector = SectorManifest.load(name=form.sector)
        lxc_id = cls._generate_id(prefix="lxc")
        password = SecretManifest.create_lxc_password(lxc_id=lxc_id, password=form.password)
        manifest = cls(
            name=lxc_id,
            metadata=LXCMetadata(
                sector_id=form.sector,
                sector_name=sector.metadata.alias,
                hostname=form.name,
                node=form.node,
            ),
            spec=LXCSpec(
                os_template=appliance.ostemplate,
                disk_storage=form.rootfs,
                disk_size=form.disk_size,
                sector=form.sector,
                memory=form.memory,
                swap=form.swap,
                cores=form.cores,
                password=password.to_ref(),
            ),
        )
        manifest.save()
        return manifest
