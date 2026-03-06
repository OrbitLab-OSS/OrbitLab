"""OrbitLab Networks Dashboard States."""

import reflex as rx

from orbitlab.manifest.sector import SectorManifest
from orbitlab.proxmox.networks import AttachedInstances
from orbitlab.web.utilities import CacheBuster, get_redis


class SectorsTableState(CacheBuster, rx.State):
    """State for managing and retrieving sector manifests in the dashboard."""

    @rx.var(deps=["_cached_sectors"])
    def sectors(self)-> list[SectorManifest]:
        """Get all existing sector manifests."""
        return [SectorManifest.load(name=name) for name in SectorManifest.get_existing()]

    @rx.var
    async def state_mapping(self) -> dict[str, str]:
        """Mapping of Sector IDs to thier states."""
        return {
            sector.name: await self._get_sector_state(sector=sector.name) or "Pending"
            for sector in self.sectors
        }

    @rx.var
    def sector_options(self) -> dict[str, str]:
        """Available Sector options used by Select-type components."""
        return {f"{sector.spec.alias} ({sector.spec.cidr_block})": sector.name for sector in self.sectors}

    @classmethod
    async def _get_sector_state(cls, sector: str) -> str:
        redis = get_redis()
        state: bytes = await redis.hget(name=f"ol:sector:{sector}", key="state")
        if state:
            return state.decode()
        return "pending"


class CreateSectorDialogState(rx.State):
    """Create Sector Dialog State."""

    form_data: rx.Field[dict] = rx.field(default_factory=dict)
    cidr_block: rx.Field[str] = rx.field(default="")


class DeleteSectorDialogState(rx.State):
    """Delete Sector Dialog State."""

    sector_id: rx.Field[str] = rx.field(default="")
    attached_vms: rx.Field[list[AttachedInstances]] = rx.field(default_factory=list)
    confirmation: rx.Field[str] = rx.field(default="")

    @rx.var
    def has_attached_compute(self) -> bool:
        """Check if there are any attached VMs to this sector."""
        return bool(self.attached_vms)

    @rx.var
    def delete_disabled(self) -> bool:
        """Check if the delete button should be disabled."""
        return self.confirmation != self.sector_id
