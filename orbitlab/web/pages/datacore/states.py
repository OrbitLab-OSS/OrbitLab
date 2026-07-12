"""DataCore States."""

import reflex as rx


class CreateDataCoreDialogState(rx.State):
    """State for DataCore Creation Dialog."""

    view_app_password: rx.Field[bool] = rx.field(default=False)


class DeleteDataCoreDialogState(rx.State):
    """State for DataCore Deletion Dialog."""

    datacore_id: str = ""
    confirmation: str = ""

    @rx.var
    def delete_disabled(self) -> bool:
        """Return True if the delete action should be disabled (name and confirmation do not match)."""
        return self.datacore_id != self.confirmation
