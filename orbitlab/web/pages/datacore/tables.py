"""DockFS Tables."""

import reflex as rx

from orbitlab.data_types import DockFSStatus, FrontendEvents
from orbitlab.redis.clients import SecretsClient
from orbitlab.redis.models import DataCore
from orbitlab.web import tailwind
from orbitlab.web.utilities import EventGroup

from .dialogs import DeleteDataCoreDialog


class DataCoreClustersTable(tailwind.Table, EventGroup):
    """A table component for displaying Conduit Pools."""

    @staticmethod
    @rx.event
    async def copy_superuser_password_to_clipboard(_: rx.State, id: str) -> FrontendEvents:
        """Copy a secret password to the clipboard."""
        secret = await SecretsClient().get_service_secret(service_name="datacore", service_id=id, subservice_name="superuser")
        return [
            rx.set_clipboard(secret),
            rx.toast.success("Copied superuser password to clipboard"),
        ]

    @classmethod
    def row(cls, datacore: DataCore) -> list[rx.Component]:
        """Create and return the table row component."""
        return [
            rx.text(datacore.config.id),
            rx.text(datacore.config.name),
            rx.text(datacore.config.replicas),
            rx.match(
                datacore.state.status,
                (DockFSStatus.AVAILABLE, tailwind.Badge(datacore.state.status.capitalize(), color_scheme="green")),
                (DockFSStatus.DEGRADED, tailwind.Badge(datacore.state.status.capitalize(), color_scheme="orange")),
                (DockFSStatus.DELETING, tailwind.Badge(datacore.state.status.capitalize(), color_scheme="red")),
                tailwind.Badge(datacore.state.status.capitalize(), color_scheme="blue"),
            ),
            rx.text(f"{datacore.config.capacity_gb}GB"),
            rx.text(datacore.config.cores),
            rx.text(f"{datacore.config.memory_gb}G"),
            tailwind.Menu(
                tailwind.Buttons.Icon("ellipsis-vertical"),
                tailwind.Menu.Item(
                    "Copy Superuser Password to Clipboard",
                    on_click=cls.copy_superuser_password_to_clipboard(datacore.config.id),
                ),
                tailwind.Menu.Separator(),
                tailwind.Menu.Item(
                    "Expand Storage",
                    disabled=True,
                    # TODO: Allow for increasing NFS data disk size
                ),
                tailwind.Menu.Separator(),
                tailwind.Menu.Item(
                    "Delete",
                    on_click=DeleteDataCoreDialog.confirm(datacore.config.id),
                    danger=True,
                ),
            ),
        ]
