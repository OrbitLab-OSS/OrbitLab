"""OrbitLab Secrets Management Dialogs."""

from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.web import components
from orbitlab.web.utilities import EventGroup

from .states import DeleteSecretDialogState, SecretsState


class DeleteSecretDialog(EventGroup):
    """Dialog component for confirming and handling the deletion of a secret."""

    @staticmethod
    @rx.event
    async def delete(state: DeleteSecretDialogState) -> FrontendEvents | None:
        """Delete the selected secret and close the dialog."""
        if state.secret:
            secret_id = state.secret_id
            state.secret.delete()
            state.reset()
            return [
                rx.toast.success(message=f"Deleted secret {secret_id}."),
                components.Dialog.close(DeleteSecretDialog.dialog_id),
                SecretsState.cache_clear("secrets"),
            ]
        return None

    @staticmethod
    @rx.event
    async def cancel(state: DeleteSecretDialogState) -> FrontendEvents:
        """Cancel the certificate authority revocation process."""
        state.reset()
        return components.Dialog.close(DeleteSecretDialog.dialog_id)

    @staticmethod
    @rx.event
    async def ensure_confirmation(state: DeleteSecretDialogState, value: str) -> None:
        """Enable or disable the delete button based on the confirmation input."""
        state.delete_disabled = value != "delete"

    dialog_id: Final = "delete-secret-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return components.Dialog(
            f"Delete {DeleteSecretDialogState.secret_id}",
            rx.el.div(
                rx.text(
                    f"You are about to delete secret `{DeleteSecretDialogState.secret_id}` and all of its versions. To "
                    "confirm this action, type 'delete' in the text box below.",
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            components.Input(
                placeholder="delete",
                on_change=cls.ensure_confirmation,
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.cancel),
                components.Buttons.Primary(
                    "Delete",
                    disabled=DeleteSecretDialogState.delete_disabled,
                    on_click=cls.delete,
                ),
                class_name="w-full flex justify-end space-x-4",
            ),
            dialog_id=cls.dialog_id,
        )
