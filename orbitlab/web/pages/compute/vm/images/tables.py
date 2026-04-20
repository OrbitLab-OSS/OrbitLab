"""OrbitLab Image Dialogs."""

import reflex as rx

from orbitlab.data_types import FrontendEvents, WorkflowStatus
from orbitlab.redis.models import BaseImage, CustomImage, ScriptStep, FileStep
from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.utilities import EventGroup, create_workflow

from .dialogs import CustomImageDialog, DeleteImageDialog, DownloadImageDialog, WorkflowLogsViewDialog
from .states import CustomImageDialogState


class BaseImagesTable(EventGroup):
    """Table component for displaying and managing base images in OrbitLab."""

    @staticmethod
    @rx.event
    async def update(_: rx.State, image_id: str) -> FrontendEvents:
        """Trigger the update process for a base image asset."""
        if error := await create_workflow(name="image.update", version="v1", payload={"id": image_id}):
            return rx.toast.error(error)
        return rx.toast.info(f"Updating {image_id}...")

    @classmethod
    def __table_row__(cls, image: BaseImage) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                rx.el.div(
                    rx.text(image.config.os),
                    rx.text(image.config.id, class_name="text-sm text-gray-500"),
                    class_name="flex-col space-y-1 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.text(f"{image.config.node}"),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.text(f"{image.config.storage}"),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.moment(image.state.download_date, local=True),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
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
                            rx.el.th("OS", class_name=header_class),
                            rx.el.th("Node", class_name=header_class),
                            rx.el.th("Storage", class_name=header_class),
                            rx.el.th("Download Date", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(OrbitLabState.base_images, lambda image: cls.__table_row__(image)),
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
            DownloadImageDialog(),
            header=tailwind.Card.Header(
                rx.el.div(
                    rx.el.h3("Base Images"),
                    rx.el.div(
                        tailwind.Buttons.Icon(
                            "refresh-ccw",
                            on_click=OrbitLabState.cache_clear("base_images"),
                        ),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between items-center",
                ),
            ),
            class_name="w-full mt-6",
        )


class CustomImagesTable(EventGroup):
    """A table component for displaying custom image manifests."""

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
    def __table_row__(cls, image: CustomImage) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                rx.el.div(
                    rx.text(image.config.name, class_name="text-base"),
                    rx.text(image.config.id, class_name="text-xs text-gray-500"),
                    class_name="flex-col space-y-1 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                image.config.base_image_id,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                tailwind.HoverCard(
                    rx.el.div(
                        rx.match(
                            image.state.worflow_status,
                            (
                                WorkflowStatus.SUCCEEDED,
                                tailwind.Badge(image.state.worflow_status.capitalize(), color_scheme="green"),
                            ),
                            (
                                WorkflowStatus.FAILED,
                                tailwind.Badge(image.state.worflow_status.capitalize(), color_scheme="red"),
                            ),
                            tailwind.Badge(image.state.worflow_status.capitalize(), color_scheme="blue"),
                        ),
                    ),
                    rx.cond(
                        rx.Var.create(image.state.last_execution).is_none(),
                        rx.text("Not Ran"),
                        rx.moment(image.state.last_execution, local=True, from_now_during=1209600000),
                    ),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                tailwind.HoverCard(
                    rx.text(rx.Var.create(image.config.steps).to(list).length(), class_name="w-full pl-10"),
                    rx.foreach(image.config.steps, lambda step, index: cls.__step_info__(step, index)),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.moment(image.config.created_on, local=True, from_now_during=1209600000),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
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
                        on_click=WorkflowLogsViewDialog.open(image.config.id),
                    ),
                    tailwind.Menu.Separator(),
                    tailwind.Menu.Item(
                        "Delete",
                        on_click=DeleteImageDialog.confirm(image.config.id),
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
                            rx.el.th("Base Image", class_name=header_class),
                            rx.el.th("Workflow Status", class_name=header_class),
                            rx.el.th("Workflow Steps", class_name=header_class),
                            rx.el.th("Date Created", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(OrbitLabState.custom_images, lambda app: cls.__table_row__(app)),
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
                WorkflowLogsViewDialog(),
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
                    rx.el.h3("Custom Images", class_name="text-center"),
                    tailwind.Buttons.Icon(
                        "refresh-ccw",
                        on_click=OrbitLabState.cache_clear("custom_images"),
                    ),
                    class_name="w-full flex justify-between items-center",
                ),
            ),
            class_name="w-full mt-6",
        )
