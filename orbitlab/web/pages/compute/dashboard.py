"""OrbitLab Compute Management Dashboard."""

import os
from typing import ClassVar, Literal

import reflex as rx

from orbitlab.proxmox import ProxmoxCompute
from orbitlab.web import tailwind

from orbitlab.web.layout import orbitlab_page
from .lxc.instances.dialogs import LaunchLXCInstanceDialog


@rx.page("/compute")
@orbitlab_page
def compute_dashboard() -> rx.Component:
    """Proxmox Nodes Page."""
    return rx.el.div(
        tailwind.PageHeader(
            "Compute Management",
            tailwind.Buttons.Primary("Create LXC", on_click=tailwind.Dialog.open(LaunchLXCInstanceDialog.dialog_id)),
        ),
        LaunchLXCInstanceDialog(),
        class_name="w-full h-full",
    )


class TerminalState(rx.State):
    """State management for the terminal component, storing VMID and compute type."""

    term_vmid: ClassVar[str]
    term_compute_type: ClassVar[Literal["qemu", "lxc"]]

    @rx.var
    async def node(self) -> str:
        """Return the Proxmox node name for the current VMID, or an empty string if unavailable."""
        if self.term_vmid:
            return await ProxmoxCompute().get_node_for_vmid(vmid=int(self.term_vmid))
        return ""

    @rx.var
    def socket_url(self) -> str:
        """Return the websocket URL for the terminal based on compute type and VMID."""
        if self.term_compute_type and self.term_vmid:
            frontend_port = os.environ["REFLEX_FRONTEND_PORT"]
            backend_port = os.environ["REFLEX_BACKEND_PORT"]
            host = self.router.url.origin.replace(frontend_port, backend_port).replace("http", "ws")
            return f"{host}/ws/terminal/{self.term_compute_type}/{self.term_vmid}"
        return ""

    @rx.var
    async def ready(self) -> bool:
        return all([self.term_vmid, await self.node, self.socket_url])


@rx.page("/terminal/[term_compute_type]/[term_vmid]")
def terminal() -> rx.Component:
    """Render the terminal page."""
    return rx.el.div(
        rx.cond(
            TerminalState.ready,
            rx.fragment(
                rx.el.div(
                    rx.text(f"VMID: {TerminalState.term_vmid}"),
                    rx.text(f"Node: {TerminalState.node}"),
                    class_name="w-full flex space-x-4 p-6",
                ),
                tailwind.Terminal(socket_url=TerminalState.socket_url),
            ),
            rx.el.div(
                tailwind.OrbitLabLogo(animated=True),
                class_name="w-full h-screen flex items-center justify-center"
            ),
        ),
        class_name="min-h-screen h-full w-full flex-col",
    )
