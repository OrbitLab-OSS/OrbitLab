"""OrbitLab Running LXC Tables."""

import reflex as rx

from orbitlab.clients.proxmox.compute.client import ProxmoxCompute
from orbitlab.data_types import FrontendEvents, LXCState, LXCStatus
from orbitlab.manifest.lxc import LXCManifest
from orbitlab.web import components
from orbitlab.web.utilities import EventGroup

from .states import LXCsState


class RunningLXCsTable(EventGroup):
    """Table component for displaying and managing running LXC appliances in OrbitLab."""

    @staticmethod
    @rx.event(background=True)
    async def run_set_lxc_status(_: rx.State, lxc: LXCManifest, status: LXCStatus) -> FrontendEvents:
        """Set the status of an LXC container asynchronously and update the frontend."""
        await rx.run_in_thread(func=lambda: ProxmoxCompute().set_lxc_status(lxc=lxc, status=status))
        match status:
            case LXCStatus.START:
                verb = "started"
            case LXCStatus.STOP:
                verb = "stopped"
            case LXCStatus.SHUTDOWN:
                verb = "shut down"
            case LXCStatus.REBOOT:
                verb = "rebooted"
        return [
            LXCsState.cache_clear("running"),
            rx.toast.success(message=f"LXC {lxc.name} {verb}."),
        ]

    @staticmethod
    @rx.event
    async def set_lxc_status(_: rx.State, lxc_id: str, status: LXCStatus) -> FrontendEvents:
        """Update the status of an LXC container and trigger backend and frontend updates."""
        lxc = LXCManifest.load(name=lxc_id)
        match status:
            case LXCStatus.START:
                lxc.spec.status = LXCState.STARTING
            case LXCStatus.STOP:
                lxc.spec.status = LXCState.STOPPED
            case LXCStatus.SHUTDOWN:
                lxc.spec.status = LXCState.STOPPED
            case LXCStatus.REBOOT:
                lxc.spec.status = LXCState.RESTARTING
        lxc.save()
        return [
            RunningLXCsTable.run_set_lxc_status(lxc, status),
            LXCsState.cache_clear("running"),
        ]

    @classmethod
    def __table_row__(cls, lxc: LXCManifest) -> rx.Component:
        """Create and return the table row component."""
        is_not_running = rx.Var.create(lxc.spec.status == LXCState.RUNNING).__invert__()
        is_not_stopped = rx.Var.create(lxc.spec.status == LXCState.STOPPED).__invert__()
        return rx.el.tr(
            rx.el.td(
                rx.el.div(
                    rx.text(lxc.name),
                    components.Badge(f"{lxc.spec.vmid}"),
                    class_name="flex space-x-4 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                lxc.metadata.hostname,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.match(
                    lxc.spec.status,
                    (LXCState.RUNNING, components.Badge(lxc.spec.status.capitalize(), color_scheme="green")),
                    (LXCState.STOPPED, components.Badge(lxc.spec.status.capitalize(), color_scheme="orange")),
                    (LXCState.TERMINATING, components.Badge(lxc.spec.status.capitalize(), color_scheme="red")),
                    components.Badge(lxc.spec.status.capitalize(), color_scheme="blue"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.el.div(
                    rx.text(lxc.metadata.sector_name),
                    components.Badge(f"{lxc.spec.sector_id}"),
                    class_name="flex space-x-4 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                lxc.spec.subnet_name,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                components.Badge(f"{lxc.spec.address}", color_scheme="blue"),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                lxc.spec.cores,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                f"{lxc.spec.memory}G ({lxc.spec.swap}G Swap)",
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                components.Menu(
                    components.Buttons.Icon("ellipsis-vertical"),
                    components.Menu.Item(
                        "Start",
                        on_click=[
                            cls.set_lxc_status(lxc.name, LXCStatus.START),
                            rx.toast.info(f"Starting {lxc.name}..."),
                        ],
                        disabled=is_not_stopped,
                    ),
                    components.Menu.Item(
                        "Reboot",
                        on_click=[
                            cls.set_lxc_status(lxc.name, LXCStatus.REBOOT),
                            rx.toast.info(f"Rebooting {lxc.name}..."),
                        ],
                        disabled=is_not_running,
                    ),
                    components.Menu.Item(
                        "Stop",
                        on_click=[
                            cls.set_lxc_status(lxc.name, LXCStatus.STOP),
                            rx.toast.info(f"Stopping {lxc.name}..."),
                        ],
                        disabled=is_not_running,
                    ),
                    components.Menu.Separator(),
                    components.Menu.Item(
                        "Terminate",
                        on_click=[
                            rx.toast.info(f"Terminating {lxc.name}..."),
                        ],
                        disabled=is_not_running & is_not_stopped,
                        danger=True,
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
                            rx.el.th("Subnet", class_name=header_class),
                            rx.el.th("Private Address", class_name=header_class),
                            rx.el.th("Cores", class_name=header_class),
                            rx.el.th("Memory", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(LXCsState.running, lambda app: cls.__table_row__(app)),
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
                    rx.el.h3("Base Appliances"),
                    rx.el.div(
                        components.Buttons.Icon("refresh-ccw", on_click=LXCsState.cache_clear("running")),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between",
                ),
            ),
            class_name="w-full mt-6",
        )
