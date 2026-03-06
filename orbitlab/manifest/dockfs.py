"""DockFS Manifests."""

from ipaddress import IPv4Interface
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import BaseModel, Field

from orbitlab.data_types import ManifestKind
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.secrets import SecretManifest

from .base import BaseManifest, Metadata, Ref, Spec
from .serialization import SerializeEnum, SerializeIP

if TYPE_CHECKING:
    from orbitlab.web.pages.dockfs.models import CreateDockFSform


class DockFsHost(BaseModel):
    """Host information for DockFS."""

    address: Annotated[IPv4Interface, SerializeIP]
    vmid: int


class DockFsMetadata(Metadata):
    """Metadata for DockFS configuration."""

    active: DockFsHost | None = None
    passive: DockFsHost | None = None

    def list_vmids(self) -> list[int]:
        """List the VM IDs of active and passive DockFS hosts."""
        if not self.active or not self.passive:
            msg = "Active or Passive DockFS node not set."
            raise ValueError(msg)
        return [self.active.vmid, self.passive.vmid]


class DockFsSpec(Spec):
    """Specification for DockFS configuration."""

    name: str
    virtual_router_id: int = Field(ge=1, le=255)
    vip: Annotated[IPv4Interface, SerializeIP]
    auth_pass: Ref
    memory_gb: int
    sockets: int
    cores: int
    capacity_gb: int
    storage: str


class DockFsManifest(BaseManifest[DockFsMetadata, DockFsSpec]):
    """Manifest for DockFS configuration."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.DOCK_FS

    def generate_active_params(self, vmid: int) -> dict[str, str]:
        """Generate parameters for the active DockFS host configuration."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        address = cluster_manifest.get_next_available_ip()
        cluster_manifest.assign_ip(address=address.ip, description=f"{self.name} node")
        self.metadata.active = DockFsHost(address=address, vmid=vmid)
        self.save()
        return {
            "vmid": vmid,
            "name": self._generate_id(prefix=self.name, count=6),
            "cores": self.spec.cores,
            "sockets": self.spec.sockets,
            "memory": self.spec.memory_gb * 1024,
            "cpu": "x86-64-v2-AES",
            "numa": 0,
            "agent": "enabled=1",
            "serial0": "socket",
            "scsi0": f"{self.spec.storage}:0,import-from={cluster_manifest.metadata.dockfs_image.volume_id}",
            "scsi1": f"{self.spec.storage}:{self.spec.capacity_gb}",
            "ide0": f"{self.spec.storage}:cloudinit",
            "citype": "nocloud",
            "ciuser": "dockfs-admin",
            "cipassword": self._get_auth_pass(),
            "net0": f"virtio,bridge={cluster_manifest.spec.backplane.vnet_id}",
            "ipconfig0": f"ip={address},gw={cluster_manifest.spec.backplane.gateway_address.ip}",
            "searchdomain": "orbitlab.internal",
            "nameserver": str(cluster_manifest.spec.backplane.dns_address.ip),
            "scsihw": "virtio-scsi-single",
            "ostype": "l26",
            "onboot": "1",
            "boot": "order=scsi0",
        }

    def generate_passive_params(self, vmid: int) -> dict[str, str]:
        """Generate parameters for the active DockFS host configuration."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        address = cluster_manifest.get_next_available_ip()
        cluster_manifest.assign_ip(address=address.ip, description=f"{self.name} node")
        self.metadata.passive = DockFsHost(address=address, vmid=vmid)
        self.save()
        return {
            "vmid": vmid,
            "name": self._generate_id(prefix=self.name, count=6),
            "cores": self.spec.cores,
            "sockets": self.spec.sockets,
            "memory": self.spec.memory_gb * 1024,
            "cpu": "x86-64-v2-AES",
            "numa": 0,
            "agent": "enabled=1",
            "serial0": "socket",
            "scsi0": f"{self.spec.storage}:0,import-from={cluster_manifest.metadata.dockfs_image.volume_id}",
            "ide0": f"{self.spec.storage}:cloudinit",
            "citype": "nocloud",
            "ciuser": "dockfs-admin",
            "cipassword": self._get_auth_pass(),
            "net0": f"virtio,bridge={cluster_manifest.spec.backplane.vnet_id}",
            "ipconfig0": f"ip={address},gw={cluster_manifest.spec.backplane.gateway_address.ip}",
            "searchdomain": "orbitlab.internal",
            "nameserver": str(cluster_manifest.spec.backplane.dns_address.ip),
            "scsihw": "virtio-scsi-single",
            "ostype": "l26",
            "onboot": "1",
            "boot": "order=scsi0",
        }

    def generate_config_command(self, config_type: Literal["active", "passive"]) -> list[str]:
        """Generate configuration parameters for DockFS service."""
        command = "create" if config_type == "active" else "create-passive"
        return ["dockfs", command, str(self.spec.vip), self.spec.virtual_router_id, self._get_auth_pass()]

    def failover(self) -> int:
        """Failover to the passive DockFS host by promoting it to active."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        cluster_manifest.release_ip(address=self.metadata.active.address.ip)
        vmid_to_terminate = self.metadata.active.vmid
        self.metadata.active = self.metadata.passive
        self.metadata.passive = None
        self.save()
        return vmid_to_terminate

    def _get_auth_pass(self) -> str:
        """Get the authentication password from the secret manifest."""
        return SecretManifest.from_ref(ref=self.spec.auth_pass).get_current_value()

    def delete(self) -> None:
        """Delete the DockFS manifest and associated secret."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        if self.metadata.passive:
            cluster_manifest.release_ip(address=self.metadata.passive.address.ip)
        if self.metadata.active:
            cluster_manifest.release_ip(address=self.metadata.active.address.ip)
        cluster_manifest.release_ip(address=self.spec.vip.ip)
        SecretManifest.from_ref(ref=self.spec.auth_pass).delete()
        super().delete()

    @classmethod
    def create(cls, form_data: "CreateDockFSform") -> Self:
        """Create a new DockFS manifest with generated configuration."""
        dockfs_id = cls._generate_id(prefix="dockfs")
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        address = cluster_manifest.get_next_available_ip()
        cluster_manifest.assign_ip(address=address.ip, description=f"VIP for {dockfs_id}", is_vip=True)
        auth_pass = SecretManifest.create_service_secret(service_name="DockFS", service_id=dockfs_id)
        manifest = cls(
            name=dockfs_id,
            metadata=DockFsMetadata(),
            spec=DockFsSpec(
                name=form_data.name,
                virtual_router_id=cls._get_available_vrid(),
                vip=address,
                auth_pass=auth_pass.to_ref(),
                memory_gb=form_data.memory,
                sockets=form_data.sockets,
                cores=form_data.cores,
                capacity_gb=form_data.capacity_gb,
                storage=form_data.storage,
            ),
        )
        manifest.save()
        return manifest

    @classmethod
    def _get_available_vrid(cls) -> int:
        used = [DockFsManifest.load(name=name).spec.virtual_router_id for name in DockFsManifest.get_existing()]
        return next(iter([vrid for vrid in range(1, 256) if vrid not in used]))
