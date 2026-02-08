"""OrbitLab Networks Dashboard States."""

import reflex as rx

from orbitlab.clients.proxmox.networks import AttachedInstances
from orbitlab.manifest.sector import SectorManifest
from orbitlab.web.utilities import CacheBuster


class SectorsState(CacheBuster, rx.State):
    """State for managing and retrieving sector manifests in the dashboard."""

    @rx.var(deps=["_cached_sectors"])
    def sectors(self)-> list[SectorManifest]:
        """Get all existing sector manifests."""
        return [SectorManifest.load(name=name) for name in SectorManifest.get_existing()]


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
