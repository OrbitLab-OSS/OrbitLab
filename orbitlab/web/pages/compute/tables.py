"""OrbitLab Running LXC Tables."""

from typing import Literal

import reflex as rx

from orbitlab.data_types import ComputeStatus, FrontendEvents, InstanceType, ProxmoxComputeStatus
from orbitlab.proxmox import Proxmox
from orbitlab.redis.models import Instance
from orbitlab.web import tailwind
from orbitlab.web.utilities import EventGroup, create_workflow

from .dialogs import TerminateInstanceDialog


class InstanceTable(tailwind.Table, EventGroup):
    
    @staticmethod
    @rx.event
    async def refresh_address(_: rx.State, id: str, instance_type: InstanceType) -> FrontendEvents:
        payload = {"id": id, "instance_type": instance_type}
        if error := await create_workflow(name="instance.acquire-ip", version="v1", payload=payload):
            return rx.toast.error(error)
        return rx.toast.info(f"Updating {id} IP...")
    
    @staticmethod
    @rx.event
    async def set_status(_: rx.State, id: str, instance_type: InstanceType, status: ProxmoxComputeStatus) -> FrontendEvents:
        """Update the status of an LXC container and trigger backend and frontend updates."""
        payload = {"instance_type": instance_type, "id": id, "desired_status": status}
        if error := await create_workflow(name="instance.state-change", version="v1", payload=payload):
            return rx.toast.error(error)
        return rx.toast.info(f"Setting {id} to {status}...")
    
    @staticmethod
    @rx.event
    async def view_in_proxmox(_: rx.State, vmid: int, compute_type: Literal["lxc", "qemu"]) -> FrontendEvents:
        return rx.redirect(
            await Proxmox().get_view_in_proxmox_url(vmid=vmid, compute_type=compute_type),
            is_external=True,
        )
    
    @classmethod
    def row(cls, instance: Instance) -> list[rx.Component]:
        """Create and return the table row component."""
        return [
            rx.text(instance.config.id),
            rx.text(instance.config.name),
            rx.cond(
                instance.state.vmid > 0,
                tailwind.Badge(f"{instance.state.vmid}"),
            ),
            rx.text(instance.config.type.upper()),
            rx.match(
                instance.state.status,
                (ComputeStatus.RUNNING, tailwind.Badge(instance.state.status.capitalize(), color_scheme="green")),
                (ComputeStatus.STOPPED, tailwind.Badge(instance.state.status.capitalize(), color_scheme="orange")),
                (ComputeStatus.TERMINATING, tailwind.Badge(instance.state.status.capitalize(), color_scheme="red")),
                tailwind.Badge(instance.state.status.capitalize(), color_scheme="blue"),
            ),
            rx.text(f"{instance.config.sector_name} ({instance.config.sector})"),
            rx.cond(
                instance.state.address,
                tailwind.Badge(instance.state.address, color_scheme="blue"),
                rx.text(" - "),
            ),
            rx.cond(
                instance.config.type == "lxc",
                rx.text(f"{instance.config.cores}"),
                tailwind.HoverCard(
                    rx.text(f"{instance.config.vcpus}", class_name="underline underline-offset-4 decoration-dashed"),
                    rx.el.div(
                        rx.text(f"{instance.config.cores}x Cores"),
                        rx.text(f"{instance.config.sockets}x Sockets"),
                        class_name="w-full flex-col align-start justify-center space-y-2",
                    ),
                ),
            ),
            rx.cond(
                instance.config.type == "lxc",
                rx.el.div(
                    rx.text(f"{instance.config.memory}G"),
                    rx.text(f"Swap: {instance.config.swap}G", class_name="text-xs text-gray-500"),
                    class_name="flex-col space-y-1 items-center",
                ),
                rx.text(f"{instance.config.memory}G"),
            ),
            tailwind.Menu(
                tailwind.Buttons.Icon("ellipsis-vertical"),
                tailwind.Menu.Item(
                    "Refresh IP",
                    on_click=cls.refresh_address(instance.config.id, instance.config.type),
                    disabled=instance.state.status != ComputeStatus.RUNNING,
                ),
                tailwind.Menu.Item(
                    "View in Proxmox",
                    on_click=cls.view_in_proxmox(instance.state.vmid, instance.config.type),
                    disabled=rx.Var.create(instance.state.vmid).is_none()
                ),
                tailwind.Menu.Separator(),
                tailwind.Menu.Item(
                    "Console",
                    on_click=rx.redirect(f"/terminal/{instance.state.vmid}", is_external=True),
                    disabled=instance.state.status != ComputeStatus.RUNNING,
                ),
                tailwind.Menu.Separator(),
                tailwind.Menu.SubMenu(
                    "Instance State",
                    tailwind.Menu.Item(
                        "Start",
                        on_click=cls.set_status(instance.config.id, instance.config.type, ProxmoxComputeStatus.START),
                        disabled=instance.state.status == ComputeStatus.RUNNING,
                    ),
                    tailwind.Menu.Item(
                        "Reboot",
                        on_click=cls.set_status(instance.config.id, instance.config.type, ProxmoxComputeStatus.REBOOT),
                        disabled=instance.state.status != ComputeStatus.RUNNING,
                    ),
                    tailwind.Menu.Item(
                        "Stop",
                        on_click=cls.set_status(instance.config.id, instance.config.type, ProxmoxComputeStatus.STOP),
                        disabled=instance.state.status != ComputeStatus.RUNNING,
                    ),
                    tailwind.Menu.Separator(),
                    tailwind.Menu.Item(
                        "Terminate",
                        on_click=TerminateInstanceDialog.confirm(instance.config.id, instance.config.type),
                        danger=True,
                    ),
                ),
            ),
        ]
