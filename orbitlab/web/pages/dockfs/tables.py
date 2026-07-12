"""DockFS Tables."""

import reflex as rx

from orbitlab.data_types import DockFSStatus
from orbitlab.redis.models import DockFS
from orbitlab.web import tailwind
from orbitlab.web.utilities import EventGroup

from .dialogs import DeleteDockFSDialog


class DockFSTable(tailwind.Table, EventGroup):
    """A table component for displaying DockFS (NFS) clusters."""

    @classmethod
    def row(cls, cluster: DockFS) -> list[rx.Component]:
        """Create and return the table row component."""
        client_code = rx.Var.create(
            f"{cluster.config.id}.sector.internal:/ /mnt nfs4 rw,hard,noatime,timeo=600,retrans=5,_netdev  0  0",
        )
        return [
            rx.text(cluster.config.id),
            rx.text(cluster.config.name),
            rx.text("Active/Passive"),
            rx.match(
                cluster.state.status,
                (DockFSStatus.AVAILABLE, tailwind.Badge(cluster.state.status.capitalize(), color_scheme="green")),
                (DockFSStatus.DEGRADED, tailwind.Badge(cluster.state.status.capitalize(), color_scheme="orange")),
                (DockFSStatus.DELETING, tailwind.Badge(cluster.state.status.capitalize(), color_scheme="red")),
                tailwind.Badge(cluster.state.status.capitalize(), color_scheme="blue"),
            ),
            rx.text(f"{cluster.config.sector_name} ({cluster.config.sector})"),
            rx.text(f"{cluster.config.capacity_gb}GB"),
            rx.text(cluster.config.vcpus),
            rx.text(f"{cluster.config.memory}G"),
            rx.el.div(
                tailwind.HoverCard(
                    tailwind.Buttons.Icon(icon="network"),
                    rx.el.div(
                        rx.text("Client fstab connection string. Click to copy."),
                        rx.text("Replace '/mnt' with your desired mountpoint."),
                        rx.el.div(
                            rx.el.code(client_code),
                            class_name=(
                                "z-10 p-3 cursor-pointer rounded-lg shadow-lg hover:border hover:border-[#36E2F4]/40 "
                                "hover:shadow-[0_0_10px_rgba(54,226,244,0.25)] transition-all duration-200 ease-in-out"
                            ),
                            on_click=[
                                rx.set_clipboard(client_code),
                                rx.toast.success("Copied to clipboard"),
                            ],
                        ),
                        class_name="w-fit flex-col space-y-6",
                    ),
                    side="left",
                    align="center",
                    avoid_collisions=True,
                ),
                tailwind.Menu(
                    tailwind.Buttons.Icon("ellipsis-vertical"),
                    tailwind.Menu.Item(
                        "Expand Storage",
                        disabled=True,
                        # TODO: Allow for increasing NFS data disk size
                    ),
                    tailwind.Menu.Separator(),
                    tailwind.Menu.Item(
                        "Delete",
                        on_click=DeleteDockFSDialog.confirm(cluster.config.id),
                        danger=True,
                    ),
                ),
                class_name="w-full flex justify-between"
            ),
        ]
