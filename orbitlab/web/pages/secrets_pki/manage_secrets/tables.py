"""OrbitLab Secrets Management Tables."""

from pathlib import Path

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.redis.clients import SecretsClient
from orbitlab.redis.models import Secret
from orbitlab.web import tailwind
from orbitlab.web.utilities import EventGroup

from .dialogs import DeleteSecretDialog
from .states import DeleteSecretDialogState


class SecretsTableState(rx.State):
    """State management for the secrets table component."""

    viewable_secrets: rx.Field[dict[str, str]] = rx.field(default_factory=dict)


class SecretsTable(tailwind.Table, EventGroup):
    """A table component for displaying secrets."""

    @staticmethod
    @rx.event
    async def view_secret(state: SecretsTableState, secret_name: str, version: int) -> None:
        """View a secret by retrieving and storing its value in the viewable secrets dictionary."""
        state.viewable_secrets[secret_name] = (await SecretsClient().get(
            secret_name=secret_name, version=version,
        )).secret_string.get_secret_value()

    @staticmethod
    @rx.event
    async def hide_secret(state: SecretsTableState, secret_name: str) -> None:
        """Hide a secret by removing it from the viewable secrets dictionary."""
        del state.viewable_secrets[secret_name]

    @staticmethod
    @rx.event
    async def open_delete_secret_dialog(state: DeleteSecretDialogState, secret: str) -> FrontendEvents:
        """Open the delete secret dialog for the specified secret."""
        state.secret = secret
        return tailwind.Dialog.open(DeleteSecretDialog.dialog_id)

    @staticmethod
    @rx.event
    async def copy_to_clipboard(_: SecretsTableState, secret_name: str, version: int) -> FrontendEvents:
        """Copy a secret value to the clipboard and show a success toast."""
        secret_value = (await SecretsClient().get(
            secret_name=secret_name, version=version,
        )).secret_string.get_secret_value()
        return [
            rx.set_clipboard(secret_value),
            rx.toast.success(f"Copied {secret_name} to clipboard"),
        ]

    @classmethod
    def row(cls, secret: Secret) -> list[rx.Component]:
        return [
            rx.text(secret.name),
            rx.text(secret.secret_version),
            rx.text(secret.description),
            rx.el.div(
                rx.cond(
                    SecretsTableState.viewable_secrets.get(secret.name, None).to(bool),
                    rx.fragment(
                        rx.text(SecretsTableState.viewable_secrets[secret.name]),
                        tailwind.Buttons.Icon(
                            icon="eye-off",
                            on_click=cls.hide_secret(secret.name),
                        ),
                    ),
                    rx.fragment(
                        rx.text("********************"),
                        tailwind.Buttons.Icon(
                            icon="eye",
                            on_click=cls.view_secret(secret.name, secret.secret_version),
                        ),
                    ),
                ),
                class_name="flex space-x-5 items-center",
            ),
            tailwind.Menu(
                tailwind.Buttons.Icon("ellipsis-vertical"),
                tailwind.Menu.Item(
                    "Copy to Clipboard",
                    on_click=cls.copy_to_clipboard(secret.name, secret.secret_version)
                ),
                tailwind.Menu.Separator(),
                tailwind.Menu.Item(
                    "Delete",
                    on_click=cls.open_delete_secret_dialog(secret.name),
                    danger=True,
                ),
            ),
        ]
