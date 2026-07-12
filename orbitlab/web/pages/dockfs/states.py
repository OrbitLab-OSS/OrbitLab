"""DockFS States."""

import reflex as rx


class DeleteDockFSDialogState(rx.State):

    name: str = ""
    confirmation: str = ""

    @rx.var
    def delete_disabled(self) -> bool:
        """Return True if the delete action should be disabled (name and confirmation do not match)."""
        return self.name != self.confirmation
