"""OrbitLab Networks Dashboard States."""

import reflex as rx

from orbitlab.proxmox.models import AttachedInstances


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
