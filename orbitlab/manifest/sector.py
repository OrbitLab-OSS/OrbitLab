"""OrbitLab Sector Manifest."""

from datetime import UTC, datetime
from ipaddress import IPv4Interface, IPv4Network
from typing import Annotated

from pydantic import BaseModel, Field

from orbitlab.data_types import ManifestKind, SectorState
from orbitlab.manifest.ipam import IpamManifest

from .base import BaseManifest, Metadata, Spec
from .ref import Ref
from .serialization import SerializeEnum, SerializeIP


class SectorMetadata(Metadata):
    """Metadata for a sector manifest."""

    alias: str
    tag: int
    state: Annotated[SectorState, SerializeEnum]


class IPAssignment(BaseModel):
    """An IP address assignment to a virtual machine or LXC."""

    address: Annotated[IPv4Interface, SerializeIP]
    vmid: str | int
    allocated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Subnet(BaseModel):
    """A subnet configuration for IP address management."""

    cidr_block: Annotated[IPv4Network, SerializeIP]
    name: str

    @property
    def default_gateway(self) -> IPv4Interface:
        """Get the gateway IP address for this subnet."""
        return IPv4Interface(f"{next(iter(self.cidr_block.hosts()))}/{self.cidr_block.prefixlen}")


class SectorSpec(Spec):
    """Spec for a sector manifest."""

    cidr_block: Annotated[IPv4Network, SerializeIP]
    subnets: list[Subnet]
    gateway_vmid: int | None = None
    dns_vmid: int | None = None
    ipam: Ref


class SectorManifest(BaseManifest[SectorMetadata, SectorSpec]):
    """A sector manifest for managing network infrastructure and IP address allocation."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.SECTOR

    @property
    def gateway_name(self) -> str:
        """Get the gateway name for this sector."""
        return f"{self.name}-gw"

    @property
    def dns_name(self) -> str:
        """Get the DNS name for this sector."""
        return f"{self.name}-dns"

    @property
    def primary_gateway(self) -> IPv4Interface:
        """Get the primary gateway interface for this sector."""
        return IPv4Interface(f"{self.spec.cidr_block.network_address + 1}/{self.spec.cidr_block.prefixlen}")

    @property
    def dns_address(self) -> IPv4Interface:
        """Get the DNS IP address for this sector."""
        return IPv4Interface(f"{self.primary_gateway.ip + 1}/{self.spec.cidr_block.prefixlen}")

    def get_subnet(self, name: str) -> Subnet:
        """Get a subnet by name."""
        return next(subnet for subnet in self.spec.subnets if subnet.name == name)

    def get_available_ips(self, subnet_name: str) -> int:
        """Return the number of available IP addresses in the specified subnet."""
        return self.get_ipam().get_subnet(name=subnet_name).available_ips()

    def set_gateway(self, vmid: int) -> None:
        """Set the gateway configuration for this sector."""
        self.spec.gateway_vmid = vmid
        self.save()

    def set_dns(self, vmid: int) -> None:
        """Set the DNS VM ID for this sector and save the manifest."""
        self.spec.dns_vmid = vmid
        self.save()

    def get_ipam(self) -> IpamManifest:
        """Load and return the IpamManifest associated with this sector."""
        return IpamManifest.load(name=self.spec.ipam.name)
