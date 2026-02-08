"""OrbitLab VM Instances Tables."""

import reflex as rx

from orbitlab.clients.proxmox.compute.client import ProxmoxCompute
from orbitlab.data_types import ComputeState, ComputeStatus, FrontendEvents
from orbitlab.manifest.compute_instances import VMManifest
from orbitlab.web import components
from orbitlab.web.utilities import EventGroup

from .states import VMInstancesTableState


class VMInstancesTable(EventGroup):
    """Table component for displaying and managing running VM appliances in OrbitLab."""

    @staticmethod
    @rx.event(background=True)
    async def update_addresses(_: rx.State) -> FrontendEvents:
        """Update the private IPv4 addresses for all existing VM manifests and clear the running cache."""
        for name in VMManifest.get_existing():
            manifest = VMManifest.load(name=name)
            if manifest.metadata.status == ComputeState.RUNNING and manifest.metadata.vmid:
                manifest.metadata.address = ProxmoxCompute().get_vm_private_ipv4(
                    node=manifest.metadata.node, vmid=manifest.metadata.vmid,
                )
                manifest.save()
        return VMInstancesTableState.cache_clear("running")

    @staticmethod
    @rx.event(background=True)
    async def run_set_vm_status(_: rx.State, vm: VMManifest, status: ComputeStatus) -> FrontendEvents:
        """Set the status of a VM asynchronously and update the frontend."""
        await rx.run_in_thread(func=lambda: ProxmoxCompute().set_vm_status(vm=vm, status=status))
        match status:
            case ComputeStatus.START:
                verb = "started"
            case ComputeStatus.STOP:
                verb = "stopped"
            case ComputeStatus.SHUTDOWN:
                verb = "shutdown"
            case ComputeStatus.REBOOT:
                verb = "rebooted"
            case ComputeStatus.TERMINATE:
                verb = "terminated"
        return [
            VMInstancesTableState.cache_clear("running"),
            rx.toast.success(message=f"VM {vm.name} {verb}."),
        ]

    @staticmethod
    @rx.event
    async def set_vm_status(_: rx.State, vm_id: str, status: ComputeStatus) -> FrontendEvents:
        """Update the status of a VM and trigger backend and frontend updates."""
        vm = VMManifest.load(name=vm_id)
        vm.set_status(status=status)
        return [
            VMInstancesTable.run_set_vm_status(vm, status),
            VMInstancesTableState.cache_clear("running"),
        ]

    @classmethod
    def __table_row__(cls, vm: VMManifest) -> rx.Component:
        """Create and return the table row component."""
        is_running = rx.Var.create(vm.metadata.status == ComputeState.RUNNING)
        is_not_stopped = rx.Var.create(vm.metadata.status == ComputeState.STOPPED).__invert__()
        return rx.el.tr(
            rx.el.td(
                rx.el.div(
                    rx.text(vm.name),
                    rx.cond(
                        rx.Var.create(vm.metadata.vmid).is_not_none(),
                        components.Badge(f"{vm.metadata.vmid}"),
                    ),
                    class_name="flex space-x-4 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                vm.metadata.name,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.match(
                    vm.metadata.status,
                    (ComputeState.RUNNING, components.Badge(vm.metadata.status.capitalize(), color_scheme="green")),
                    (ComputeState.STOPPED, components.Badge(vm.metadata.status.capitalize(), color_scheme="orange")),
                    (ComputeState.TERMINATING, components.Badge(vm.metadata.status.capitalize(), color_scheme="red")),
                    components.Badge(label=vm.metadata.status.capitalize(), color_scheme="blue"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.el.div(
                    rx.text(vm.spec.sector),
                    class_name="flex space-x-4 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.cond(
                    rx.Var.create(vm.metadata.address).is_not_none(),
                    components.Badge(f"{vm.metadata.address}", color_scheme="blue"),
                    components.Badge("N/A", color_scheme="blue"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                components.HoverCard(
                    rx.text(f"{vm.spec.vcpus}", class_name="text-[#1E63E9] dark:text-[#36E2F4]"),
                    rx.el.div(
                        rx.text(f"{vm.spec.cores}x Cores"),
                        rx.text(f"{vm.spec.sockets}x Sockets"),
                        class_name="w-full flex-col align-start justify-center space-y-2",
                    ),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                f"{vm.spec.memory}G",
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                components.Menu(
                    components.Buttons.Icon("ellipsis-vertical"),
                    components.Menu.Item(
                        "Console",
                        on_click=rx.redirect(f"/terminal/qemu/{vm.metadata.vmid}", is_external=True),
                        disabled=vm.metadata.status != ComputeState.RUNNING,
                    ),
                    components.Menu.SubMenu(
                        "Instance State",
                        components.Menu.Item(
                            "Start",
                            on_click=[
                                cls.set_vm_status(vm.name, ComputeStatus.START),
                                rx.toast.info(f"Starting {vm.name}..."),
                            ],
                            disabled=is_running,
                        ),
                        components.Menu.Item(
                            "Reboot",
                            on_click=[
                                cls.set_vm_status(vm.name, ComputeStatus.REBOOT),
                                rx.toast.info(f"Rebooting {vm.name}..."),
                            ],
                            disabled=is_running.__invert__(),
                        ),
                        components.Menu.Item(
                            "Stop",
                            on_click=[
                                cls.set_vm_status(vm.name, ComputeStatus.STOP),
                                rx.toast.info(f"Stopping {vm.name}..."),
                            ],
                            disabled=is_running.__invert__(),
                        ),
                        components.Menu.Separator(),
                        components.Menu.Item(
                            "Terminate",
                            on_click=[
                                cls.set_vm_status(vm.name, ComputeStatus.TERMINATE),
                                rx.toast.info(f"Terminating {vm.name}..."),
                            ],
                            disabled=is_running.__invert__() & is_not_stopped,
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
        return components.Card(
            rx.el.div(
                rx.el.table(
                    rx.el.thead(
                        rx.el.tr(
                            rx.el.th("ID", class_name=header_class),
                            rx.el.th("Hostname", class_name=header_class),
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
                        rx.foreach(VMInstancesTableState.running, lambda app: cls.__table_row__(app)),
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
            header=components.Card.Header(
                rx.el.div(
                    rx.el.div(),
                    rx.el.div(
                        components.Buttons.Icon("refresh-ccw", on_click=cls.update_addresses),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between items-center",
                ),
            ),
            class_name="w-full mt-6",
        )
