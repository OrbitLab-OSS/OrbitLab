"""OrbitLab Compute Management Dashboard."""

import os
from typing import ClassVar

import reflex as rx

from orbitlab.proxmox import Proxmox
from orbitlab.web import tailwind

from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.layout import orbitlab_page

from .dialogs import LaunchComputeInstanceDialog, TerminateInstanceDialog
from .tables import InstanceTable


@rx.page("/compute")
@orbitlab_page
def compute_instances() -> rx.Component:
    return rx.el.div(
        tailwind.PageHeader(
            "Compute Instances",
            tailwind.Buttons.Primary("Create LXC", on_click=LaunchComputeInstanceDialog.open("lxc")),
            tailwind.Buttons.Primary("Create VM", on_click=LaunchComputeInstanceDialog.open("qemu")),
        ),
        InstanceTable(
            name="Instances",
            headers=["Instance ID", "Name", "VMID", "Type", "Status", "Sector", "Address", "CPU", "Memory", ""],
            data=OrbitLabState.instances,
            refresh=OrbitLabState.cache_clear("instances")
        ),
        LaunchComputeInstanceDialog(),
        TerminateInstanceDialog(),
        class_name="w-full h-full",
    )


class TerminalState(rx.State):
    """State management for the terminal component, storing VMID and compute type."""

    term_vmid: ClassVar[str]

    @rx.var
    async def node(self) -> str:
        """Return the Proxmox node name for the current VMID, or an empty string if unavailable."""
        if self.term_vmid:
            resource = await Proxmox().get_compute_resource(vmid=int(self.term_vmid))
            return resource.node
        return ""

    @rx.var
    def socket_url(self) -> str:
        """Return the websocket URL for the terminal based on compute type and VMID."""
        if self.term_vmid:
            frontend_port = os.environ["REFLEX_FRONTEND_PORT"]
            backend_port = os.environ["REFLEX_BACKEND_PORT"]
            host = self.router.url.origin.replace(frontend_port, backend_port).replace("http", "ws")
            return f"{host}/ws/terminal/{self.term_vmid}"
        return ""

    @rx.var
    async def ready(self) -> bool:
        return all([self.term_vmid, await self.node, self.socket_url])


@rx.page("/terminal/[term_vmid]")
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
