"""OrbitLab Secrets Management Tables."""

from pathlib import Path

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.manifest.secrets import SecretManifest
from orbitlab.services.vault.client import SecretVault
from orbitlab.web import components
from orbitlab.web.states.manifests import ManifestsState
from orbitlab.web.states.utilities import EventGroup


class SecretsTableState(rx.State):
    """State management for the secrets table component."""

    viewable_secrets: rx.Field[dict[str, str]] = rx.field(default_factory=dict)


class SecretsTable(EventGroup):
    """A table component for displaying virtual networks in the dashboard."""

    @staticmethod
    @rx.event
    async def view_secret(state: SecretsTableState, secret_name: str, version: int) -> None:
        """View a secret by retrieving and storing its value in the viewable secrets dictionary."""
        state.viewable_secrets[secret_name] = SecretVault().get(
            secret_name=Path(secret_name), version=version,
        ).secret_string.get_secret_value()

    @staticmethod
    @rx.event
    async def hide_secret(state: SecretsTableState, secret_name: str) -> None:
        """Hide a secret by removing it from the viewable secrets dictionary."""
        del state.viewable_secrets[secret_name]

    @staticmethod
    @rx.event
    async def copy_to_clipboard(_: SecretsTableState, secret_name: str, version: int) -> FrontendEvents:
        """Copy a secret value to the clipboard and show a success toast."""
        secret_value = SecretVault().get(
            secret_name=Path(secret_name), version=version,
        ).secret_string.get_secret_value()
        return [
            rx.set_clipboard(secret_value),
            rx.toast.success(f"Copied {secret_name} to clipboard"),
        ]

    @classmethod
    def __table_row__(cls, secret: SecretManifest) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                secret.spec.secret_name,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                secret.spec.version,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                secret.metadata.description,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.el.div(
                    rx.cond(
                        SecretsTableState.viewable_secrets.get(secret.spec.secret_name, None).to(bool),
                        rx.fragment(
                            rx.text(SecretsTableState.viewable_secrets[secret.spec.secret_name]),
                            components.Buttons.Icon(
                                icon="eye-off",
                                on_click=cls.hide_secret(secret.spec.secret_name),
                            ),
                        ),
                        rx.fragment(
                            rx.text("********************"),
                            components.Buttons.Icon(
                                icon="eye",
                                on_click=cls.view_secret(secret.spec.secret_name, secret.spec.version),
                            ),
                        ),
                    ),
                    components.Buttons.Icon(
                        icon="copy",
                        on_click=cls.copy_to_clipboard(secret.spec.secret_name, secret.spec.version),
                    ),
                    class_name="flex space-x-5 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            class_name=(
                "transition-colors duration-200 "
                "hover:bg-gray-100/60 dark:hover:bg-white/[0.06] "
                "hover:text-gray-900 dark:hover:text-[#E8F1FF]"
            ),
        )

    def __new__(cls) -> rx.Component:
        """Create and return the appliance templates table component."""
        header_class = (
            "px-6 py-3 text-left text-xs font-semibold tracking-wider uppercase text-gray-600 dark:text-[#AEB9CC]"
        )
        return components.Card(
            rx.el.div(
                rx.el.table(
                    rx.el.thead(
                        rx.el.tr(
                            rx.el.th("ID", class_name=header_class),
                            rx.el.th("Version", class_name=header_class),
                            rx.el.th("Description", class_name=header_class),
                            rx.el.th("Value", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(ManifestsState.secrets, lambda secret: cls.__table_row__(secret)),
                        class_name=(
                            "divide-y divide-gray-200 dark:divide-white/[0.08] bg-white/70 dark:bg-[#0E1015]/60 "
                            "backdrop-blur-sm"
                        ),
                    ),
                    class_name=(
                        "min-w-full text-sm text-gray-800 dark:text-gray-200 "
                        "divide-y divide-gray-200 dark:divide-white/[0.08]"
                    ),
                ),
                class_name=(
                    "border border-gray-200 dark:border-white/[0.08] "
                    "rounded-b-xl overflow-x-auto shadow-md "
                    "bg-gradient-to-b from-white/90 to-gray-50/70 "
                    "dark:from-[#0E1015]/80 dark:to-[#12141A]/80 "
                    "hover:ring-1 hover:ring-[#36E2F4]/40 "
                    "transition-all duration-200"
                ),
            ),
            header=components.Card.Header(
                rx.el.div(
                    rx.el.h3("Secrets"),
                    rx.el.div(
                        components.Buttons.Icon("refresh-ccw", on_click=ManifestsState.cache_clear("secrets")),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between",
                ),
            ),
            class_name="w-full mt-6",
        )
