"""DockFS Tables."""

import reflex as rx

from orbitlab.data_types import DockFSStatus
from orbitlab.redis.models import DockFS
from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.utilities import EventGroup

from .dialogs import DeleteDockFSDialog


class DockFSTable(EventGroup):
    """Table component for displaying and managing DockFS (NFS) clusters in OrbitLab."""

    @classmethod
    def __table_row__(cls, cluster: DockFS) -> rx.Component:
        """Create and return the table row component."""
        client_code = rx.Var.create(
            f"{cluster.config.id}.orbitlab.internal:/ /mnt nfs4 rw,hard,noatime,timeo=600,retrans=5,_netdev  0  0",
        )
        return rx.el.tr(
            rx.el.td(
                rx.el.div(
                    rx.text(cluster.config.name),
                    rx.text(cluster.config.id, class_name="text-sm text-gray-500"),
                    class_name="flex-col space-y-1 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.text("Active/Passive"),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.match(
                    cluster.state.status,
                    (DockFSStatus.AVAILABLE, tailwind.Badge(cluster.state.status.capitalize(), color_scheme="green")),
                    (DockFSStatus.DEGRADED, tailwind.Badge(cluster.state.status.capitalize(), color_scheme="orange")),
                    (DockFSStatus.DELETING, tailwind.Badge(cluster.state.status.capitalize(), color_scheme="red")),
                    tailwind.Badge(cluster.state.status.capitalize(), color_scheme="blue"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.text(f"{cluster.config.capacity_gb}GB"),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.text(cluster.config.vcpus),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.text(f"{cluster.config.memory_gb}G"),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
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
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
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
        return tailwind.Card(
            rx.el.div(
                rx.el.table(
                    rx.el.thead(
                        rx.el.tr(
                            rx.el.th("ID", class_name=header_class),
                            rx.el.th("Mode", class_name=header_class),
                            rx.el.th("Status", class_name=header_class),
                            rx.el.th("Capacity", class_name=header_class),
                            rx.el.th("vCPUs", class_name=header_class),
                            rx.el.th("Memory", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(OrbitLabState.dockfs_clusters, lambda app: cls.__table_row__(app)),
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
            header=tailwind.Card.Header(
                rx.el.div(
                    rx.el.div(),
                    rx.el.div(
                        tailwind.Buttons.Icon("refresh-ccw", on_click=OrbitLabState.cache_clear("dockfs_clusters")),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between",
                ),
            ),
            class_name="w-full mt-6",
        )
