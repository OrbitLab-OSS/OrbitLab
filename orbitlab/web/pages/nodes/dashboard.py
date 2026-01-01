"""Dashboard module for displaying and managing Proxmox nodes."""

import reflex as rx

from orbitlab.manifest.nodes import NodeManifest
from orbitlab.web.components import Card
from orbitlab.web.utilities import EventGroup

from .layout import nodes_page
from .states import ProxmoxState


class NodeRow(EventGroup):
    """Factory class for creating table row components for Proxmox nodes."""

    def __new__(cls, node: NodeManifest) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                node.name,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.cond(
                    node.metadata.online,
                    rx.cond(
                        node.metadata.maintenance_mode,
                        rx.badge("Maintenance", color_scheme="yellow"),
                        rx.badge("Online", color_scheme="green"),
                    ),
                    rx.badge("Offline", color_scheme="red"),
                ),
                class_name="px-6 py-4 whitespace-nowrap",
            ),
            rx.el.td(
                node.metadata.ip,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                # TODO: Per-node menu options
                class_name="px-6 py-4 whitespace-nowrap",
            ),
            class_name=(
                "transition-colors duration-200 "
                "hover:bg-gray-100/60 dark:hover:bg-white/[0.06] "
                "hover:text-gray-900 dark:hover:text-[#E8F1FF]"
            ),
        )


@rx.page("/nodes")
@nodes_page
def nodes_dashboard() -> rx.Component:
    """Proxmox Nodes Page."""
    return rx.el.div(
        Card(
            rx.el.div(
                rx.el.table(
                    # === Table Header ===
                    rx.el.thead(
                        rx.el.tr(
                            rx.el.th(
                                "Name",
                                class_name=(
                                    "px-6 py-3 text-left text-xs font-semibold tracking-wider "
                                    "uppercase text-gray-600 dark:text-[#AEB9CC]"
                                ),
                            ),
                            rx.el.th(
                                "Status",
                                class_name=(
                                    "px-6 py-3 text-left text-xs font-semibold tracking-wider "
                                    "uppercase text-gray-600 dark:text-[#AEB9CC]"
                                ),
                            ),
                            rx.el.th(
                                "IPv4 Address",
                                class_name=(
                                    "px-6 py-3 text-left text-xs font-semibold tracking-wider "
                                    "uppercase text-gray-600 dark:text-[#AEB9CC]"
                                ),
                            ),
                            rx.el.th(
                                "",
                                class_name=(
                                    "px-6 py-3 text-left text-xs font-semibold tracking-wider "
                                    "uppercase text-gray-600 dark:text-[#AEB9CC]"
                                ),
                            ),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(ProxmoxState.nodes, lambda node: NodeRow(node)),
                        class_name=(
                            "divide-y divide-gray-200 dark:divide-white/[0.08] "
                            "bg-white/70 dark:bg-[#0E1015]/60 backdrop-blur-sm"
                        ),
                    ),
                    class_name=(
                        "min-w-full text-sm text-gray-800 dark:text-gray-200 "
                        "divide-y divide-gray-200 dark:divide-white/[0.08]"
                    ),
                ),
                class_name=(
                    "border border-gray-200 dark:border-white/[0.08] "
                    "rounded-b-xl overflow-hidden shadow-md "
                    "bg-gradient-to-b from-white/90 to-gray-50/70 "
                    "dark:from-[#0E1015]/80 dark:to-[#12141A]/80 "
                    "hover:ring-1 hover:ring-[#36E2F4]/40 "
                    "transition-all duration-200"
                ),
            ),
            header=Card.Header(rx.el.h3("Proxmox Nodes")),
            class_name="w-full",
        ),
        class_name="w-full flex",
    )
