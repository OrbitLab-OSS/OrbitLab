"""OrbitLab Secrets Management Dialogs."""

from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.redis.clients import SecretsClient
from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.utilities import EventGroup

from .states import CreateSecretDialogState, DeleteSecretDialogState


class CreateSecretDialog(EventGroup):

    @staticmethod
    @rx.event
    async def create_secret(_: rx.State, form: dict) -> FrontendEvents:
        await SecretsClient().create(
            secret_name=form["secret_name"],
            value=form["secret_value"],
            description=form.get("description", ""),
        )
        return [
            CreateSecretDialog.close,
            OrbitLabState.cache_clear("secrets"),
        ]

    @staticmethod
    @rx.event
    async def toggle_view_secret(state: CreateSecretDialogState) -> None:
        state.view_secret_value = not state.view_secret_value

    @staticmethod
    @rx.event
    async def close(state: CreateSecretDialogState) -> FrontendEvents:
        """Cancel the secret creation process and close the dialog."""
        state.reset()
        return tailwind.Dialog.close(CreateSecretDialog.dialog_id)
    
    dialog_id: Final = "create-secret-dialog"
    form_id: Final = "create-secret-form"
    
    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return tailwind.Dialog(
            "Create New Secret",
            rx.el.form(
                tailwind.FieldSet(
                    "Secret Configuration",
                    tailwind.FieldSet.Field(
                        "Secret Name: ",
                        tailwind.Input(
                            placeholder="my/secret-name or /my/super/secret_value/",
                            pattern=r"[A-Za-z0-9_\/\-]+",
                            error=(
                                "Names must be alphanumeric characters. "
                                "Only the special characters in the brackets are allowed: [/_-]"
                            ),
                            auto_complete="off",
                            form=cls.form_id,
                            name="secret_name",
                            required=True,
                            class_name="w-full"
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Description: ",
                        tailwind.Input(
                            placeholder="My description of my secret.",
                            auto_complete="off",
                            form=cls.form_id,
                            name="description",
                            class_name="w-full"
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Value: ",
                        rx.el.div(
                            tailwind.Input(
                                placeholder="My Secret Value",
                                type=rx.cond(CreateSecretDialogState.view_secret_value, "text", "password"), # pyright: ignore[reportArgumentType]
                                form=cls.form_id,
                                name="secret_value",
                                required=True,
                                class_name="w-full"
                            ),
                            rx.cond(
                                CreateSecretDialogState.view_secret_value,
                                tailwind.Buttons.Icon("eye-off", on_click=cls.toggle_view_secret, form=""),
                                tailwind.Buttons.Icon("eye", on_click=cls.toggle_view_secret, form=""),
                            ),
                            class_name="w-full flex space-x-4 items-center"
                        )
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.create_secret,
            ),
            rx.el.div(
                tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                tailwind.Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex justify-end space-x-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-[40vw]",
        )


class DeleteSecretDialog(EventGroup):
    """Dialog component for confirming and handling the deletion of a secret."""

    @staticmethod
    @rx.event
    async def delete(state: DeleteSecretDialogState) -> FrontendEvents | None:
        """Delete the selected secret and close the dialog."""
        if state.secret:
            await SecretsClient().delete(secret_name=state.secret)
            state.reset()
            return [
                rx.toast.success(message=f"Deleted secret {state.secret}."),
                DeleteSecretDialog.close,
                OrbitLabState.cache_clear("secrets"),
            ]
        return None

    @staticmethod
    @rx.event
    async def close(state: DeleteSecretDialogState) -> FrontendEvents:
        """Cancel the certificate authority revocation process."""
        state.reset()
        return tailwind.Dialog.close(DeleteSecretDialog.dialog_id)

    @staticmethod
    @rx.event
    async def ensure_confirmation(state: DeleteSecretDialogState, value: str) -> None:
        """Enable or disable the delete button based on the confirmation input."""
        state.delete_disabled = value != "delete"

    dialog_id: Final = "delete-secret-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return tailwind.Dialog(
            f"Delete {DeleteSecretDialogState.secret}",
            rx.el.div(
                rx.text(
                    f"You are about to delete secret `{DeleteSecretDialogState.secret}` and all of its versions. To "
                    "confirm this action, type 'delete' in the text box below.",
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            tailwind.Input(
                placeholder="delete",
                on_change=cls.ensure_confirmation,
            ),
            rx.el.div(
                tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                tailwind.Buttons.Primary(
                    "Delete",
                    disabled=DeleteSecretDialogState.delete_disabled,
                    on_click=cls.delete,
                ),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )
