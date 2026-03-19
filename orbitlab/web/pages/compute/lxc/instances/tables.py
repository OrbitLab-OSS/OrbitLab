"""OrbitLab Running LXC Tables."""

import reflex as rx

from orbitlab.data_types import ComputeState, ComputeStatus
from orbitlab.manifest.compute_instances.lxc import LXCManifest
from orbitlab.web import components
from orbitlab.web.pages.compute.lxc.instances.dialogs import TerminateLXCInstanceDialog
from orbitlab.web.utilities import EventGroup, get_worker

from .states import LXCInstancesTableState


class LXCInstancesTable(EventGroup):
    """Table component for displaying and managing running LXC appliances in OrbitLab."""

    @staticmethod
    @rx.event
    async def set_lxc_status(_: rx.State, manifest: str, status: ComputeStatus) -> None:
        """Update the status of an LXC container and trigger backend and frontend updates."""
        worker = get_worker()
        error = await worker.create_workflow(
            name="lxc.state-change",
            version="v1",
            payload={"manifest": manifest, "desired_status": status},
        )
        if error:
            return rx.toast.error(error)
        return rx.toast.info(f"Setting {manifest} to {status}...")

    @classmethod
    def __table_row__(cls, instance: LXCManifest) -> rx.Component:
        """Create and return the table row component."""
        status = LXCInstancesTableState.state_map.get(instance.name, "pending").to(str)
        address = LXCInstancesTableState.address_map.get(instance.name).to(str)
        is_running = status == ComputeState.RUNNING
        is_not_stopped = (status == ComputeState.STOPPED).__invert__()
        return rx.el.tr(
            rx.el.td(
                rx.el.div(
                    rx.el.div(
                        rx.text(instance.metadata.hostname),
                        rx.cond(
                            rx.Var.create(instance.metadata.vmid) > 0,
                            components.Badge(f"{instance.metadata.vmid}"),
                        ),
                        class_name="flex space-x-4 items-center",
                    ),
                    rx.text(instance.name, class_name="text-xs text-gray-500"),
                    class_name="flex-col space-y-1 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.match(
                    status,
                    (ComputeState.RUNNING, components.Badge(status.capitalize(), color_scheme="green")),
                    (ComputeState.STOPPED, components.Badge(status.capitalize(), color_scheme="orange")),
                    (ComputeState.TERMINATING, components.Badge(status.capitalize(), color_scheme="red")),
                    components.Badge(status.capitalize(), color_scheme="blue"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.el.div(
                    rx.text(instance.metadata.sector_name),
                    components.Badge(f"{instance.spec.sector}"),
                    class_name="flex space-x-4 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.cond(
                    address.is_not_none(),
                    components.Badge(address, color_scheme="blue"),
                    components.Badge("N/A", color_scheme="blue"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                instance.spec.cores,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                f"{instance.spec.memory}G",
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                f"{instance.spec.swap}G",
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                components.Menu(
                    components.Buttons.Icon("ellipsis-vertical"),
                    components.Menu.Item(
                        "Console",
                        on_click=rx.redirect(f"/terminal/lxc/{instance.metadata.vmid}", is_external=True),
                        disabled=status != ComputeState.RUNNING,
                    ),
                    components.Menu.SubMenu(
                        "Instance State",
                        components.Menu.Item(
                            "Start",
                            on_click=cls.set_lxc_status(instance.name, ComputeStatus.START),
                            disabled=is_running,
                        ),
                        components.Menu.Item(
                            "Reboot",
                            on_click=cls.set_lxc_status(instance.name, ComputeStatus.REBOOT),
                            disabled=is_running.__invert__(),
                        ),
                        components.Menu.Item(
                            "Stop",
                            on_click=cls.set_lxc_status(instance.name, ComputeStatus.STOP),
                            disabled=is_running.__invert__(),
                        ),
                        components.Menu.Separator(),
                        components.Menu.Item(
                            "Terminate",
                            on_click=TerminateLXCInstanceDialog.confirm(instance.name),
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
                            rx.el.th("LXC Instance", class_name=header_class),
                            rx.el.th("Status", class_name=header_class),
                            rx.el.th("Sector", class_name=header_class),
                            rx.el.th("Private Address", class_name=header_class),
                            rx.el.th("Cores", class_name=header_class),
                            rx.el.th("Memory", class_name=header_class),
                            rx.el.th("Swap", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(LXCInstancesTableState.running, lambda app: cls.__table_row__(app)),
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
                TerminateLXCInstanceDialog(),
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
                        components.Buttons.Icon("refresh-ccw", on_click=LXCInstancesTableState.cache_clear("running")),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between",
                ),
            ),
            class_name="w-full mt-6",
        )
