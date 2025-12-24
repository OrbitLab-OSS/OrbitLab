"""OrbitLab Sector Manifest."""

from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv4Interface, IPv4Network
from typing import Annotated

from pydantic import BaseModel, Field

from orbitlab.data_types import ManifestKind, SectorState

from .base import BaseManifest, Metadata, Spec
from .ref import Ref
from .serialization import SerializeEnum, SerializeIP, SerializeIPList


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
    assignments: Annotated[list[IPAssignment], Field(default_factory=list)]

    @property
    def default_gateway(self) -> IPv4Interface:
        """Get the gateway IP address for this subnet."""
        return IPv4Interface(f"{next(iter(self.cidr_block.hosts()))}/{self.cidr_block.prefixlen}")


class Gateway(BaseModel):
    """A gateway configuration for sector network infrastructure."""

    backplane_address: Annotated[IPv4Interface, SerializeIP]
    vmid: str | int
    password: Ref
    sector_addresses: Annotated[list[IPv4Interface], SerializeIPList]


class SectorSpec(Spec):
    """Spec for a sector manifest."""

    cidr_block: Annotated[IPv4Network, SerializeIP]
    subnets: list[Subnet]
    gateway: Gateway | None = None
    ipam: Ref


class SectorManifest(BaseManifest[SectorMetadata, SectorSpec]):
    """A sector manifest for managing network infrastructure and IP address allocation."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.SECTOR

    @property
    def gateway_name(self) -> str:
        """Get the gateway name for this sector."""
        return f"{self.name}gw"

    @property
    def primary_gateway(self) -> IPv4Address:
        """Get the primary gateway IP address for this sector."""
        return next(iter(self.spec.cidr_block.hosts()))

    def get_subnet(self, name: str) -> Subnet:
        """Get a subnet by name."""
        return next(subnet for subnet in self.spec.subnets if subnet.name == name)

    def set_gateway(self, backplane_address: IPv4Interface, vmid: str, password_ref: Ref) -> None:
        """Set the gateway configuration for this sector."""
        self.spec.gateway = Gateway(
            backplane_address=backplane_address,
            vmid=vmid,
            password=password_ref,
            sector_addresses=[subnet.default_gateway for subnet in self.spec.subnets],
        )
        self.save()

    def get_gateway(self) -> Gateway:
        """Get the gateway configuration for this sector."""
        if self.spec.gateway:
            return self.spec.gateway
        raise ValueError
