"""Dashboard module for displaying and managing Proxmox nodes."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import reflex as rx
from reflex.utils.prerequisites import get_and_validate_app

from orbitlab.data_types import NodeStatus
from orbitlab.manifest.schemas.nodes import NodeManifest
from orbitlab.web.components import Card, SideBar
from orbitlab.web.states.cluster import ProxmoxNodesState


@rx.event(background=True)
async def refresh_nodes(state: ProxmoxNodesState) -> None:
    """Background task that periodically refreshes Proxmox nodes data.

    Parameters:
        state (ProxmoxNodesState): The Proxmox nodes state instance containing refresh configuration.
    """
    app_info = get_and_validate_app()
    while state.router.session.client_token in app_info.app.event_namespace.token_to_sid:
        await asyncio.sleep(state.refresh_rate)
        async with state:
            state.refresh_nodes = True


@rx.event
async def on_load(state: ProxmoxNodesState) -> AsyncGenerator[rx.event.EventCallback, Any, None]:  # noqa: ARG001
    """Load event handler that starts the background node refresh task.

    Parameters:
        state (ProxmoxNodesState): The Proxmox nodes state instance.
    """
    yield refresh_nodes


class Dashboard:
    """Dashboard component for displaying Proxmox nodes in a table format.

    This class provides a visual representation of Proxmox nodes with their
    status, uptime, CPU utilization, and memory utilization metrics.
    """

    @classmethod
    def _node_table_row(cls, node: NodeManifest) -> rx.Component:
        return rx.el.tr(
            rx.el.td(
                node.name,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.match(
                    node.metadata.status,
                    (NodeStatus.ONLINE, rx.badge("Online", color_scheme="green")),
                    (NodeStatus.ONLINE, rx.badge("Online", color_scheme="green")),
                ),
                class_name="px-6 py-4 whitespace-nowrap",
            ),
            # rx.el.td(
            #     rx.moment(datetime.now(UTC).timestamp() - node.uptime, unix=True, from_now=True),
            #     class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            # ),
            # rx.el.td(
            #     ProgressBars.Basic(node.cpu_utilization * 100, start_label="0%", end_label="100%"),
            #     class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            # ),
            # rx.el.td(
            #     ProgressBars.Basic(
            #         node.used_memory / node.total_memory * 100,
            #         start_label="0GB",
            #         end_label=f"{node.total_mem_gb}GB",
            #     ),
            #     class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            # ),
            class_name=(
                "transition-colors duration-200 "
                "hover:bg-gray-100/60 dark:hover:bg-white/[0.06] "
                "hover:text-gray-900 dark:hover:text-[#E8F1FF]"
            ),
        )

    def __new__(cls) -> rx.Component:
        """Create and return the dashboard component displaying Proxmox nodes in a table."""
        return rx.flex(
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
                                # rx.el.th(
                                #     "Uptime",
                                #     class_name=(
                                #         "px-6 py-3 text-left text-xs font-semibold tracking-wider "
                                #         "uppercase text-gray-600 dark:text-[#AEB9CC]"
                                #     ),
                                # ),
                                # rx.el.th(
                                #     "CPU Utilization",
                                #     class_name=(
                                #         "px-6 py-3 text-left text-xs font-semibold tracking-wider "
                                #         "uppercase text-gray-600 dark:text-[#AEB9CC]"
                                #     ),
                                # ),
                                # rx.el.th(
                                #     "Memory Utilization",
                                #     class_name=(
                                #         "px-6 py-3 text-left text-xs font-semibold tracking-wider "
                                #         "uppercase text-gray-600 dark:text-[#AEB9CC]"
                                #     ),
                                # ),
                            ),
                            class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                        ),
                        rx.el.tbody(
                            rx.foreach(ProxmoxNodesState.nodes, lambda node: cls._node_table_row(node)),
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
        )


@rx.page("/nodes", on_load=on_load)
def nodes_page() -> rx.Component:
    """Proxmox Nodes Page."""
    side_bar, sidebar_id = SideBar(
        SideBar.NavItem(icon="layout-dashboard", text="Dashboard"),
        default_page="Dashboard",
        title="Nodes",
    )
    return rx.el.div(
        side_bar,
        rx.el.div(
            rx.match(
                SideBar.Manager.registered[sidebar_id].active_page,
                ("Dashboard", Dashboard()),
                Dashboard(),
            ),
            class_name=(
                "min-h-screen w-full flex flex-col p-4 "
                "bg-gradient-to-b from-gray-200 to-gray-400 "
                "dark:from-[#111317] dark:to-[#151820] "
                "text-gray-800 dark:text-[#E8F1FF] "
                "selection:bg-[#36E2F4]/40 selection:text-white "
                "backdrop-blur-sm transition-colors duration-300 ease-in-out"
            ),
        ),
        class_name="min-h-screen w-full flex",
    )
