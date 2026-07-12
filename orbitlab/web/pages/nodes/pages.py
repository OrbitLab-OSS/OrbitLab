"""Dashboard module for displaying and managing Proxmox nodes."""

import reflex as rx

from orbitlab.redis.models import Node
from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.utilities import EventGroup
from orbitlab.web.layout import orbitlab_page


class NodeRow(EventGroup):
    """Factory class for creating table row components for Proxmox nodes."""

    def __new__(cls, node: Node) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                node.config.name,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.cond(
                    node.state.online,
                    rx.cond(
                        node.state.maintenance_mode,
                        rx.badge("Maintenance", color_scheme="yellow"),
                        rx.badge("Online", color_scheme="green"),
                    ),
                    rx.badge("Offline", color_scheme="red"),
                ),
                class_name="px-6 py-4 whitespace-nowrap",
            ),
            rx.el.td(
                node.config.address,
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
@orbitlab_page
def nodes_dashboard() -> rx.Component:
    """Proxmox Nodes Page."""
    return rx.el.div(
        tailwind.Card(
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
                        rx.foreach(OrbitLabState.nodes, lambda node: NodeRow(node)),
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
            header=tailwind.Card.Header(
                rx.el.div(
                    rx.el.h3("Proxmox Nodes"),
                    rx.el.div(
                        tailwind.Buttons.Icon("refresh-ccw", on_click=OrbitLabState.cache_clear("nodes")),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between",
                )
                
            ),
            class_name="w-full",
        ),
        class_name="w-full flex",
    )
