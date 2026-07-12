"""OrbitLab LXC Tables."""

import reflex as rx

from orbitlab.data_types import FrontendEvents, TemplateWorkflowStatus
from orbitlab.redis.models import BaseAppliance, CustomAppliance, ScriptStep, FileStep
from orbitlab.web import tailwind
from orbitlab.web.utilities import EventGroup, create_workflow

from .dialogs import CustomApplianceDialog, CustomApplianceState, DeleteApplianceDialog, WorkflowLogsViewDialog


class BaseApplianceTable(tailwind.Table, EventGroup):
    """A table component for displaying base appliances."""

    @staticmethod
    @rx.event
    async def re_download_appliance(_: rx.State, appliance_id: str) -> FrontendEvents:
        """Re-download the specified appliance by name."""
        if error := await create_workflow(name="appliance.download", version="v1", payload={"id": appliance_id, "update": True}):
            return rx.toast.error(error)
        return rx.toast.info(f"Updating {appliance_id}...")

    @classmethod
    def row(cls, appliance: BaseAppliance) -> list[rx.el.Td]:
        """Create and return the table row component."""
        return [
            rx.text(appliance.config.id),
            rx.text(appliance.config.template),
            rx.text(appliance.config.node),
            rx.text(appliance.config.storage),
            rx.moment(appliance.state.download_date, from_now_during=172800, format="YYYY-MM-DD HH:mm:ss"),
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
        ]


class CustomApplianceTable(tailwind.Table, EventGroup):
    """A table component for displaying custom appliances."""

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
    def row(cls, appliance: CustomAppliance) -> list[rx.el.Td]:
        """Create and return the table row component."""
        return [
            tailwind.HoverCard(
                rx.text(appliance.config.id, class_name="text-base underline underline-offset-4 decoration-dashed"),
                rx.el.div(
                    rx.text(f"Source (ID): {appliance.config.base_appliance_id}", class_name="text-sm"),
                    rx.text(f"Source (Volume ID): {appliance.config.base_volume_id}", class_name="text-xs text-gray-500"),
                    class_name="flex-col space-y-1 items-center",
                ),
            ),
            rx.text(appliance.config.name),
            rx.match(
                appliance.state.workflow_status,
                (
                    TemplateWorkflowStatus.SUCCEEDED,
                    tailwind.Badge(appliance.state.workflow_status.capitalize(), color_scheme="green"),
                ),
                (
                    TemplateWorkflowStatus.FAILED,
                    tailwind.Badge(appliance.state.workflow_status.capitalize(), color_scheme="red"),
                ),
                tailwind.Badge(appliance.state.workflow_status.capitalize(), color_scheme="blue"),
            ),
            tailwind.HoverCard(
                rx.text(rx.Var.create(appliance.config.steps).to(list).length(), class_name="w-full pl-10"),
                rx.foreach(appliance.config.steps, lambda step, index: cls.__step_info__(step, index)),
            ),
            rx.moment(appliance.config.created_on, local=True, from_now_during=1209600000),
            rx.cond(
                rx.Var.create(appliance.state.last_execution).is_none(),
                rx.text(" - "),
                rx.moment(appliance.state.last_execution, local=True, from_now_during=1209600000),
            ),
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
        ]
