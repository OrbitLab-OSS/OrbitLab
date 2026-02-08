"""Schema definitions for LXC container manifests in OrbitLab."""

from ipaddress import IPv4Interface
from typing import TYPE_CHECKING, Annotated, Self

from pydantic import computed_field

from orbitlab.data_types import ComputeState, ComputeStatus, ManifestKind
from orbitlab.manifest.base import BaseManifest, Metadata, Spec
from orbitlab.manifest.ref import Ref
from orbitlab.manifest.secrets import SecretManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.manifest.serialization import SerializeEnum, SerializeIP
from orbitlab.services.vault.client import SecretVault

if TYPE_CHECKING:
    from orbitlab.web.pages.compute.vm.instances.models import CreateVMForm


class VMMetadata(Metadata):
    """Metadata schema for Proxmox VM resources in OrbitLab."""

    name: str
    on_boot: bool = True
    status: Annotated[ComputeState, SerializeEnum] = ComputeState.STARTING
    node: str
    address: Annotated[IPv4Interface, SerializeIP] | None = None
    vmid: int | None = None


class VMSpec(Spec):
    """Specification schema for Proxmox VM resources in OrbitLab."""

    cores: int
    sockets: int
    memory: int
    image: str
    disk_storage: str
    disk_size: int
    sector: str
    user: str = "root"
    password: Ref

    @computed_field(repr=False)
    @property
    def vcpus(self) -> int:
        """Return the total number of virtual CPUs (cores * sockets) for the VM."""
        return self.cores * self.sockets


class VMManifest(BaseManifest[VMMetadata, VMSpec]):
    """Manifest schema and logic for managing Proxmox VMs in OrbitLab."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.VM

    def create_vm_params(self, vmid: int) -> dict[str, int | str]:
        """Generate the parameters required to create a VM in Proxmox."""
        self.metadata.vmid = vmid
        self.save()
        dns_address = SectorManifest.load(name=self.spec.sector).dns_address
        return {
            "vmid": vmid,
            "name": self.metadata.name,
            "cores": self.spec.cores,
            "sockets": self.spec.sockets,
            "memory": self.spec.memory * 1024,
            "cpu": "x86-64-v2-AES",
            "numa": 0,
            "agent": "enabled=1",
            "serial0": "socket",
            "scsi0": f"{self.spec.disk_storage}:0,import-from={self.spec.image}",
            "ide0": f"{self.spec.disk_storage}:cloudinit",
            "citype": "nocloud",
            "ciuser": self.spec.user,
            "cipassword": self.get_password(),
            "net0": f"virtio,bridge={self.spec.sector}",
            "ipconfig0": "ip=dhcp",
            "searchdomain": "sector.internal",
            "nameserver": f"{dns_address.ip}",
            "scsihw": "virtio-scsi-single",
            "ostype": "l26",
            "onboot": "1" if self.metadata.on_boot else "0",
            "boot": "order=scsi0",
        }

    def get_password(self) -> str:
        """Retrieve the current password value from the referenced secret manifest."""
        if self.spec.password:
            return SecretManifest.load(name=self.spec.password.name).get_current_value()
        return ""

    def launched(self, vmid: int) -> None:
        """Update the manifest to reflect that the container has been launched."""
        self.metadata.vmid = vmid
        self.metadata.status = ComputeState.RUNNING
        self.save()

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
        """Delete the VM manifest, and remove its associated secret."""
        SecretManifest.load(name=self.spec.password.name).delete()
        super().delete()

    @classmethod
    def create(cls, form_data: "CreateVMForm") -> Self:
        """Create a new VMManifest instance from the provided CreateVMForm data."""
        vm_id = cls._generate_id(prefix="vm")
        if not form_data.password:
            form_data.password = SecretVault.generate_random_password()
        password = SecretManifest.create_vm_password(vm_id=vm_id, password=form_data.password)
        manifest = cls(
            name=vm_id,
            metadata=VMMetadata(
                name=form_data.name,
                node=form_data.node,
            ),
            spec=VMSpec(
                cores=form_data.cores,
                sockets=form_data.sockets,
                memory=form_data.memory,
                image=form_data.volume_id,
                disk_storage=form_data.storage,
                disk_size=form_data.disk_size,
                sector=form_data.sector,
                password=password.to_ref(),
            ),
        )
        manifest.save()
        return manifest
