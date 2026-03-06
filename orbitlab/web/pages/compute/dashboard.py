"""OrbitLab Compute Management Dashboard."""

from typing import ClassVar, Literal

import reflex as rx

from orbitlab.proxmox import ProxmoxCompute
from orbitlab.web import components

from orbitlab.web.layout import orbitlab_page
from .lxc.instances.dialogs import LaunchApplianceDialog


@rx.page("/compute")
@orbitlab_page
def compute_dashboard() -> rx.Component:
    """Proxmox Nodes Page."""
    return rx.el.div(
        components.PageHeader(
            "Compute Management",
            components.Buttons.Primary("Create LXC", on_click=components.Dialog.open(LaunchApplianceDialog.dialog_id)),
        ),
        LaunchApplianceDialog(),
        class_name="w-full h-full",
    )


class TerminalState(rx.State):
    """State management for the terminal component, storing VMID and compute type."""

    term_vmid: ClassVar[str]
    term_compute_type: ClassVar[Literal["qemu", "lxc"]]

    @rx.var
    def node(self) -> str:
        """Return the Proxmox node name for the current VMID, or an empty string if unavailable."""
        if self.term_vmid:
            return ProxmoxCompute().get_node_for_vmid(vmid=int(self.term_vmid))
        return ""

    @rx.var
    def socket_url(self) -> str:
        """Return the websocket URL for the terminal based on compute type and VMID."""
        if self.term_compute_type and self.term_vmid:
            host = self.router.url.origin.replace("3000", "8000").replace("http", "ws")
            return f"{host}/ws/terminal/{self.term_compute_type}/{self.term_vmid}"
        return ""


@rx.page("/terminal/[term_compute_type]/[term_vmid]")
def terminal() -> rx.Component:
    """Render the terminal page."""
    return rx.el.div(
        rx.el.div(
            rx.text(f"VMID: {TerminalState.term_vmid}"),
            rx.text(f"Node: {TerminalState.node}"),
            class_name="w-full flex space-x-4 p-6",
        ),
        components.Terminal(socket_url=TerminalState.socket_url),
        class_name="min-h-screen h-full w-full flex-col",
    )
