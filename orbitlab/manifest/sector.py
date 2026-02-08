"""OrbitLab Sector Manifest."""

from ipaddress import IPv4Interface, IPv4Network
from typing import TYPE_CHECKING, Annotated, Self

from orbitlab.data_types import ManifestKind, SectorState

from .base import BaseManifest, Metadata, Spec
from .serialization import SerializeEnum, SerializeIP

if TYPE_CHECKING:
    from orbitlab.web.pages.sectors.dashboard.models import CreateSectorForm


class SectorMetadata(Metadata):
    """Metadata for a sector manifest."""

    alias: str
    tag: int
    state: Annotated[SectorState, SerializeEnum]


class SectorSpec(Spec):
    """Spec for a sector manifest."""

    cidr_block: Annotated[IPv4Network, SerializeIP]
    gateway_vmid: int | None = None


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

    def set_gateway(self, vmid: int) -> None:
        """Set the gateway configuration for this sector."""
        self.spec.gateway_vmid = vmid
        self.save()

    @classmethod
    def create(cls, form_data: "CreateSectorForm") -> Self:
        """Create and save a new SectorManifest from form data."""
        manifest = cls(
            name=form_data.sector_id,
            metadata=SectorMetadata(
                alias=form_data.name,
                tag=form_data.tag,
                state=SectorState.PENDING,
            ),
            spec=SectorSpec(
                cidr_block=IPv4Network(form_data.cidr_block),
            ),
        )
        manifest.save()
        return manifest
