"""OrbitLab VM Instances Tables."""

import reflex as rx

from orbitlab.data_types import ComputeStatus, ProxmoxComputeStatus, FrontendEvents
from orbitlab.redis.models import VMInstance
from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.utilities import EventGroup, create_workflow

from .dialogs import TerminateVMInstanceDialog


class VMInstancesTable(EventGroup):
    """Table component for displaying and managing running VM appliances in OrbitLab."""

    @staticmethod
    @rx.event
    async def set_vm_status(_: rx.State, manifest: str, status: ProxmoxComputeStatus) -> FrontendEvents:
        """Update the status of a VM and trigger backend and frontend updates."""
        payload = {"manifest": manifest, "desired_status": status.value}
        if error := await create_workflow(name="vm.state-change", version="v1", payload=payload):
            return rx.toast.error(error)
        return rx.toast.info(f"Setting {manifest} to {status}...")

    @classmethod
    def __table_row__(cls, instance: VMInstance) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                rx.el.div(
                    rx.el.div(
                        rx.text(instance.config.id),
                        rx.cond(
                            instance.state.vmid,
                            tailwind.Badge(f"{instance.state.vmid}"),
                        ),
                        class_name="flex space-x-4 items-center",
                    ),
                    rx.text(instance.config.id, class_name="text-xs text-gray-500"),
                    class_name="flex-col space-y-1 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.match(
                    instance.state.status,
                    (ComputeStatus.RUNNING, tailwind.Badge(instance.state.status.capitalize(), color_scheme="green")),
                    (ComputeStatus.STOPPED, tailwind.Badge(instance.state.status.capitalize(), color_scheme="orange")),
                    (ComputeStatus.TERMINATING, tailwind.Badge(instance.state.status.capitalize(), color_scheme="red")),
                    tailwind.Badge(instance.state.status.capitalize(), color_scheme="blue"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.el.div(
                    rx.text(instance.config.sector_name),
                    tailwind.Badge(f"{instance.config.sector}"),
                    class_name="flex space-x-4 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.cond(
                    instance.state.address,
                    tailwind.Badge(instance.state.address, color_scheme="blue"),
                    tailwind.Badge(label=" - ", color_scheme="blue"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                tailwind.HoverCard(
                    rx.text(f"{instance.config.vcpus}", class_name="text-[#1E63E9] dark:text-[#36E2F4]"),
                    rx.el.div(
                        rx.text(f"{instance.config.cores}x Cores"),
                        rx.text(f"{instance.config.sockets}x Sockets"),
                        class_name="w-full flex-col align-start justify-center space-y-2",
                    ),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                f"{instance.config.memory}G",
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                tailwind.Menu(
                    tailwind.Buttons.Icon("ellipsis-vertical"),
                    tailwind.Menu.Item(
                        "Console",
                        on_click=rx.redirect(f"/terminal/qemu/{instance.state.vmid}", is_external=True),
                        disabled=instance.state.status != ComputeStatus.RUNNING,
                    ),
                    tailwind.Menu.SubMenu(
                        "Instance State",
                        tailwind.Menu.Item(
                            "Start",
                            on_click=cls.set_vm_status(instance.config.id, ProxmoxComputeStatus.START),
                            disabled=instance.state.status == ComputeStatus.RUNNING,
                        ),
                        tailwind.Menu.Item(
                            "Reboot",
                            on_click=cls.set_vm_status(instance.config.id, ProxmoxComputeStatus.REBOOT),
                            disabled=instance.state.status != ComputeStatus.RUNNING,
                        ),
                        tailwind.Menu.Item(
                            "Stop",
                            on_click=cls.set_vm_status(instance.config.id, ProxmoxComputeStatus.STOP),
                            disabled=instance.state.status != ComputeStatus.RUNNING,
                        ),
                        tailwind.Menu.Separator(),
                        tailwind.Menu.Item(
                            "Terminate",
                            on_click=TerminateVMInstanceDialog.confirm(instance.config.id),
                            danger=True,
                        ),
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
                            rx.el.th("VM Instance", class_name=header_class),
                            rx.el.th("Status", class_name=header_class),
                            rx.el.th("Sector", class_name=header_class),
                            rx.el.th("Private Address", class_name=header_class),
                            rx.el.th("vCPUs", class_name=header_class),
                            rx.el.th("Memory", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(OrbitLabState.vm_instances, lambda app: cls.__table_row__(app)),
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
                TerminateVMInstanceDialog(),
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
                        tailwind.Buttons.Icon("refresh-ccw", on_click=OrbitLabState.cache_clear("vm_instances")),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between items-center",
                ),
            ),
            class_name="w-full mt-6",
        )
