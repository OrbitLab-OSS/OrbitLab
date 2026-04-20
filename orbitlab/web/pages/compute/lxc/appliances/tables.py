"""OrbitLab LXC Tables."""

import reflex as rx

from orbitlab.data_types import FrontendEvents, WorkflowStatus
from orbitlab.redis.models import BaseAppliance, CustomAppliance, ScriptStep, FileStep
from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.utilities import EventGroup, create_workflow

from .dialogs import CustomApplianceDialog, CustomApplianceState, DeleteApplianceDialog, WorkflowLogsViewDialog


class BaseApplianceTable(EventGroup):
    """A table component for displaying base appliance manifests."""

    @staticmethod
    @rx.event
    async def re_download_appliance(_: rx.State, appliance_id: str) -> FrontendEvents:
        """Re-download the specified appliance by name."""
        if error := await create_workflow(name="appliance.download", version="v1", payload={"id": appliance_id, "update": True}):
            return rx.toast.error(error)
        return rx.toast.info(f"Updating {appliance_id}...")

    @classmethod
    def __table_row__(cls, appliance: BaseAppliance) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                rx.el.div(
                    rx.text(appliance.config.template, class_name="text-base"),
                    rx.text(appliance.config.id, class_name="text-xs text-gray-500"),
                    class_name="flex-col space-y-1 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                appliance.config.node,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                appliance.config.storage,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.moment(appliance.state.download_date, from_now_during=172800, format="YYYY-MM-DD HH:mm:ss"),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                tailwind.Menu(
                    tailwind.Buttons.Icon("ellipsis-vertical"),
                    tailwind.Menu.Item(
                        "Re-Download",
                        on_click=BaseApplianceTable.re_download_appliance(appliance.config.id),
                    ),
                    tailwind.Menu.Item(
                        "Create Custom Appliance",
                        on_click=CustomApplianceDialog.start_appliance_creation(appliance.config.id),
                    ),
                    tailwind.Menu.Separator(),
                    tailwind.Menu.Item(
                        "Delete",
                        on_click=DeleteApplianceDialog.confirm(appliance.config.id),
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
        return tailwind.Card(
            rx.el.div(
                rx.el.table(
                    rx.el.thead(
                        rx.el.tr(
                            rx.el.th("Name", class_name=header_class),
                            rx.el.th("Node", class_name=header_class),
                            rx.el.th("Storage", class_name=header_class),
                            rx.el.th("Date Downloaded", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(OrbitLabState.base_appliances, lambda app: cls.__table_row__(app)),
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
            header=tailwind.Card.Header(
                rx.el.div(
                    rx.el.h3("Base Appliances", class_name="text-center"),
                    rx.el.div(
                        tailwind.Buttons.Icon(
                            "refresh-ccw",
                            on_click=OrbitLabState.cache_clear("base_appliances"),
                        ),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between items-center",
                ),
            ),
            class_name="w-full mt-6",
        )


class CustomApplianceTable(EventGroup):
    """A table component for displaying custom appliance manifests."""

    @staticmethod
    @rx.event
    async def edit_appliance(state: CustomApplianceState, appliance_id: str) -> FrontendEvents:
        """Edit a custom appliance by name and open the dialog."""
        state.edit_mode = True
        return [
            CustomApplianceState.load_appliance(appliance_id),
            tailwind.Dialog.open(CustomApplianceDialog.dialog_id),
        ]

    @classmethod
    def __step_info__(cls, step: ScriptStep | FileStep, index: int) -> rx.Component:
        """Create a component displaying step information with index and type badge."""
        return rx.el.div(
            rx.text(f"{index + 1}. {step.name} ", rx.el.span(tailwind.Badge(step.type, color_scheme="blue"))),
            class_name="w-fit p-2 flex-col space-y-2",
        )

    @classmethod
    def __table_row__(cls, appliance: CustomAppliance) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                rx.el.div(
                    rx.text(appliance.config.name, class_name="text-base"),
                    rx.text(appliance.config.id, class_name="text-xs text-gray-500"),
                    class_name="flex-col space-y-1 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.text(appliance.config.base_appliance_id),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                tailwind.HoverCard(
                    rx.el.div(
                        rx.match(
                            appliance.state.worflow_status,
                            (
                                WorkflowStatus.SUCCEEDED,
                                tailwind.Badge(appliance.state.worflow_status.capitalize(), color_scheme="green"),
                            ),
                            (
                                WorkflowStatus.FAILED,
                                tailwind.Badge(appliance.state.worflow_status.capitalize(), color_scheme="red"),
                            ),
                            tailwind.Badge(appliance.state.worflow_status.capitalize(), color_scheme="blue"),
                        ),
                    ),
                    rx.cond(
                        rx.Var.create(appliance.state.last_execution).is_none(),
                        rx.text("Not Ran"),
                        rx.moment(appliance.state.last_execution, local=True, from_now_during=1209600000),
                    ),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                tailwind.HoverCard(
                    rx.text(rx.Var.create(appliance.config.steps).to(list).length(), class_name="w-full pl-10"),
                    rx.foreach(appliance.config.steps, lambda step, index: cls.__step_info__(step, index)),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.moment(appliance.config.created_on, local=True, from_now_during=1209600000),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                tailwind.Menu(
                    tailwind.Buttons.Icon("ellipsis-vertical"),
                    tailwind.Menu.Item(
                        "Edit",
                        on_click=CustomApplianceTable.edit_appliance(appliance.config.id),
                    ),
                    tailwind.Menu.Item(
                        "Rerun Workflow",
                        on_click=CustomApplianceDialog.run_workflow(appliance.config.id),
                    ),
                    tailwind.Menu.Separator(),
                    tailwind.Menu.Item(
                        "View Logs",
                        on_click=WorkflowLogsViewDialog.view_workflow_logs(appliance.config.id),
                    ),
                    tailwind.Menu.Separator(),
                    tailwind.Menu.Item(
                        "Delete",
                        on_click=DeleteApplianceDialog.confirm(appliance.config.id),
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
        return tailwind.Card(
            rx.el.div(
                rx.el.table(
                    rx.el.thead(
                        rx.el.tr(
                            rx.el.th("Name", class_name=header_class),
                            rx.el.th("Base Appliance", class_name=header_class),
                            rx.el.th("Trusted CAs", class_name=header_class),
                            rx.el.th("Workflow Status", class_name=header_class),
                            rx.el.th("Workflow Steps", class_name=header_class),
                            rx.el.th("Date Created", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(OrbitLabState.custom_appliances, lambda app: cls.__table_row__(app)),
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
            CustomApplianceDialog(),
            WorkflowLogsViewDialog(),
            header=tailwind.Card.Header(
                rx.el.div(
                    rx.el.h3("Custom Appliances", class_name="text-center"),
                    tailwind.Buttons.Icon(
                        "refresh-ccw",
                        on_click=OrbitLabState.cache_clear("custom_appliances"),
                    ),
                    class_name="w-full flex justify-between items-center",
                ),
            ),
            class_name="w-full mt-6",
        )
