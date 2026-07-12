"""OrbitLab Image Dialogs."""

import reflex as rx

from orbitlab.data_types import FrontendEvents, WorkflowStatus
from orbitlab.redis.models import BaseImage, CustomImage, ScriptStep, FileStep
from orbitlab.web import tailwind
from orbitlab.web.utilities import EventGroup, create_workflow

from .dialogs import CustomImageDialog, DeleteImageDialog, WorkflowLogsViewDialog
from .states import CustomImageDialogState


class BaseImagesTable(tailwind.Table, EventGroup):
    """Table component for displaying and managing base images in OrbitLab."""

    @staticmethod
    @rx.event
    async def update(_: rx.State, image_id: str) -> FrontendEvents:
        """Trigger the update process for a base image asset."""
        if error := await create_workflow(name="image.update", version="v1", payload={"id": image_id}):
            return rx.toast.error(error)
        return rx.toast.info(f"Updating {image_id}...")

    @classmethod
    def row(cls, image: BaseImage) -> list[rx.Component]:
        """Create and return the table row component."""
        return [
            rx.text(image.config.id),
            rx.text(image.config.os),
            rx.text(image.config.node),
            rx.text(image.config.storage),
            rx.cond(
                image.state.download_date,
                rx.moment(image.state.download_date, local=True),
                rx.text(" - "),
            ),
            tailwind.Menu(
                tailwind.Buttons.Icon("ellipsis-vertical"),
                tailwind.Menu.Item(
                    "Create Custom Image",
                    on_click=CustomImageDialog.start_image_creation(image.config.id),
                ),
                tailwind.Menu.Item("Update", on_click=cls.update(image.config.id)),
                tailwind.Menu.Separator(),
                tailwind.Menu.Item(
                    "Delete",
                    on_click=DeleteImageDialog.confirm(image.config.id),
                    danger=True,
                ),
            ),
        ]


class CustomImagesTable(tailwind.Table, EventGroup):
    """A table component for displaying custom images."""

    @staticmethod
    @rx.event
    async def edit_image(state: CustomImageDialogState, image_id: str) -> FrontendEvents:
        """Edit a custom appliance by name and open the dialog."""
        state.edit_mode = True
        return [
            CustomImageDialogState.load_image(image_id),
            tailwind.Dialog.open(CustomImageDialog.dialog_id),
        ]

    @classmethod
    def __step_info__(cls, step: ScriptStep | FileStep, index: int) -> rx.Component:
        """Create a component displaying step information with index and type badge."""
        return rx.el.div(
            rx.text(f"{index + 1}. {step.name} ", rx.el.span(tailwind.Badge(step.type, color_scheme="blue"))),
            class_name="w-fit p-2 flex-col space-y-2",
        )

    @classmethod
    def row(cls, image: CustomImage) -> list[rx.Component]:
        """Create and return the table row component."""
        return [
            rx.text(image.config.id),
            rx.text(image.config.name),
            tailwind.HoverCard(
                rx.text(image.config.base_image_id, class_name="underline underline-offset-4 decoration-dashed"),
                rx.text(image.config.base_volume_id),
            ),
            tailwind.HoverCard(
                rx.el.div(
                    rx.match(
                        image.state.workflow_status,
                        (
                            WorkflowStatus.SUCCEEDED,
                            tailwind.Badge(image.state.workflow_status.capitalize(), color_scheme="green"),
                        ),
                        (
                            WorkflowStatus.FAILED,
                            tailwind.Badge(image.state.workflow_status.capitalize(), color_scheme="red"),
                        ),
                        tailwind.Badge(image.state.workflow_status.capitalize(), color_scheme="blue"),
                    ),
                ),
                rx.cond(
                    rx.Var.create(image.state.last_execution).is_none(),
                    rx.text("Not Ran"),
                    rx.moment(image.state.last_execution, local=True, from_now_during=1209600000),
                ),
            ),
            tailwind.HoverCard(
                rx.text(rx.Var.create(image.config.steps).to(list).length(), class_name="w-full pl-10"),
                rx.foreach(image.config.steps, lambda step, index: cls.__step_info__(step, index)),
            ),
            rx.moment(image.config.created_on, local=True, from_now_during=1209600000),
            tailwind.Menu(
                tailwind.Buttons.Icon("ellipsis-vertical"),
                tailwind.Menu.Item(
                    "Edit",
                    on_click=CustomImagesTable.edit_image(image.config.id),
                ),
                tailwind.Menu.Item(
                    "Rerun Workflow",
                    on_click=CustomImageDialog.run_workflow(image.config.id),
                ),
                tailwind.Menu.Separator(),
                tailwind.Menu.Item(
                    "View Logs",
                    on_click=WorkflowLogsViewDialog.view_workflow_logs(image.config.id),
                ),
                tailwind.Menu.Separator(),
                tailwind.Menu.Item(
                    "Delete",
                    on_click=DeleteImageDialog.confirm(image.config.id),
                    danger=True,
                ),
            ),
        ]
