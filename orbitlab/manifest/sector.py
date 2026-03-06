"""OrbitLab Sector Manifest."""

from ipaddress import IPv4Address, IPv4Interface, IPv4Network
from typing import TYPE_CHECKING, Annotated, Self

from pydantic import BaseModel, Field

from orbitlab import constants
from orbitlab.data_types import ManifestKind
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.services import SecretVault

from .base import BaseManifest, Metadata, Spec
from .serialization import SerializeEnum, SerializeIP

if TYPE_CHECKING:
    from orbitlab.web.pages.sectors.dashboard.models import CreateSectorForm


class SectorMetadata(Metadata):
    """Metadata for a sector manifest."""

    gateway_vmid: int | None = None
    gateway_appliance: str = ""
    backplane_address: Annotated[IPv4Interface, SerializeIP] | None = None


class SectorVIP(BaseModel):
    """Sector VIP Assignment."""

    virtual_router_id: int
    address: Annotated[IPv4Interface, SerializeIP]


class SectorSpec(Spec):
    """Spec for a sector manifest."""

    cidr_block: Annotated[IPv4Network, SerializeIP]
    alias: str
    tag: int
    vips: list[SectorVIP] = Field(default_factory=list)

    def get_vip_by_vrid(self, vrid: int) -> SectorVIP | None:
        """Get a VIP by its virtual router ID."""
        return next(iter(vip for vip in self.vips if vip.virtual_router_id == vrid), None)

    def get_vip_by_address(self, address: IPv4Address) -> SectorVIP | None:
        """Get a VIP by its IP address."""
        return next(iter(vip for vip in self.vips if vip.address.ip == address), None)


class SectorManifest(BaseManifest[SectorMetadata, SectorSpec]):
    """A sector manifest for managing network infrastructure and IP address allocation."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.SECTOR

    @property
    def gateway_name(self) -> str:
        """Get the gateway name for this sector."""
        return f"{self.name}-gw"

    @property
    def default_gateway(self) -> IPv4Interface:
        """Get the primary gateway interface for this sector."""
        return IPv4Interface(f"{self.spec.cidr_block.network_address + 1}/{self.spec.cidr_block.prefixlen}")

    @property
    def dns_address(self) -> IPv4Interface:
        """Get the DNS IP address for this sector."""
        return IPv4Interface(f"{self.spec.cidr_block.network_address + 2}/{self.spec.cidr_block.prefixlen}")

    def generate_gateway_params(self, vmid: int, storage: str) -> dict[str, str]:
        """Generate gateway parameters for container deployment."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        self.metadata.backplane_address = cluster_manifest.get_next_available_ip()
        self.metadata.gateway_vmid = vmid
        cluster_manifest.assign_ip(
            address=self.metadata.backplane_address.ip,
            description=f"Sector {self.name} gateway",
        )
        self.metadata.gateway_appliance = cluster_manifest.metadata.sector_gateway_appliance.volume_id
        self.save()
        return {
            "features": "nesting=1",
            "ostemplate": self.metadata.gateway_appliance,
            "hostname": self.gateway_name,
            "cores": "1",
            "memory": "512",
            "swap": "512",
            "net0": f"name=eth0,bridge={self.name},ip={self.default_gateway.with_prefixlen}",
            "net1": (
                "name=eth1,"
                f"bridge={cluster_manifest.spec.backplane.vnet_id},"
                f"ip={self.metadata.backplane_address},"
                f"gw={cluster_manifest.spec.backplane.gateway_address.ip}"
            ),
            "net2": f"name=eth2,bridge={self.name},ip={self.dns_address.with_prefixlen}",
            "rootfs": f"{storage}:8",
            "unprivileged": "1",
            "vmid": vmid,
            "password": SecretVault.generate_random_password(),
            "searchdomain": "sector.internal",
            "nameserver": str(cluster_manifest.spec.backplane.dns_address.ip),
            "onboot": "1",
        }

    def assign_vip(self) -> SectorVIP:
        """Assign the next available the VIP."""
        used_vrids = [vip.virtual_router_id for vip in self.spec.vips]
        used_vips = [vip.address.ip for vip in self.spec.vips]
        vrid = next(iter(i for i in range(1,256) if i not in used_vrids))
        # First two are Default GW and DNS, respectively
        useable = list(self.spec.cidr_block.hosts())[2:constants.NetworkSettings.RESERVED_SECTOR_IPS]
        address = next(iter(addr for addr in useable if addr not in used_vips))
        assigned_vip = SectorVIP(
            virtual_router_id=vrid,
            address=IPv4Interface(f"{address}/{self.spec.cidr_block.prefixlen}"),
        )
        self.spec.vips.append(assigned_vip)
        self.save()
        return assigned_vip

    def release_vip(self, vrid: int) -> None:
        """Release the VIP assigned to the specified Virtual Router ID."""
        vip = self.spec.get_vip_by_vrid(vrid=vrid)
        if vip:
            self.spec.vips.remove(vip)
            self.save()

    @classmethod
    def create(cls, form_data: "CreateSectorForm") -> Self:
        """Create and save a new SectorManifest from form data."""
        manifest = cls(
            name=form_data.sector_id,
            metadata=SectorMetadata(),
            spec=SectorSpec(
                cidr_block=IPv4Network(form_data.cidr_block),
                alias=form_data.name,
                tag=form_data.tag,
            ),
        )
        manifest.save()
        return manifest

    def delete(self) -> None:
        """Delete the sector manifest and release its backplane IP address."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        cluster_manifest.set_tag_as_unused(tag=self.spec.tag)
        if self.metadata.backplane_address:
            cluster_manifest.release_ip(address=self.metadata.backplane_address.ip)
        return super().delete()
