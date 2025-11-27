"""Dashboard module for displaying and managing Proxmox nodes."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import reflex as rx
from reflex.utils.prerequisites import get_and_validate_app

from orbitlab.data_types import NodeStatus
from orbitlab.manifest.schemas.nodes import NodeManifest
from orbitlab.web.components import Card
from orbitlab.web.states.cluster import ProxmoxNodesState

from .layout import nodes_page


@rx.event(background=True)
async def refresh_nodes(state: ProxmoxNodesState) -> None:
    """Background task that periodically refreshes Proxmox nodes data."""
    app_info = get_and_validate_app()
    while state.router.session.client_token in app_info.app.event_namespace.token_to_sid:
        await asyncio.sleep(state.refresh_rate)
        async with state:
            state.refresh_nodes = True


@rx.event
async def on_load(state: ProxmoxNodesState) -> AsyncGenerator[rx.event.EventCallback, Any, None]:  # noqa: ARG001
    """Load event handler that starts the background node refresh task."""
    yield refresh_nodes


class NodeRow:
    """Factory class for creating table row components for Proxmox nodes."""

    def __new__(cls, node: NodeManifest) -> rx.Component:
        """Create and return the table row component."""
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
            class_name=(
                "transition-colors duration-200 "
                "hover:bg-gray-100/60 dark:hover:bg-white/[0.06] "
                "hover:text-gray-900 dark:hover:text-[#E8F1FF]"
            ),
        )


@rx.page("/nodes", on_load=on_load)
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
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(ProxmoxNodesState.nodes, lambda node: NodeRow(node)),
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
