"""OrbitLab Image Dialogs."""

import reflex as rx

from orbitlab.clients.proxmox.compute.client import ProxmoxCompute
from orbitlab.clients.proxmox.compute.models import Asset
from orbitlab.data_types import FrontendEvents, WorkflowStatus
from orbitlab.manifest.compute_templates import FileStep, ScriptStep
from orbitlab.manifest.compute_templates.images import BaseImageManifest, CustomImageManifest
from orbitlab.web import components
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.utilities import EventGroup

from .dialogs import CustomImageDialog, DownloadImageDialog
from .states import BaseImagesTableState, CustomImageDialogState, CustomImagesTableState, DownloadImageDialogState


class BaseImagesTable(EventGroup):
    """Table component for displaying and managing base images in OrbitLab."""

    @staticmethod
    @rx.event
    async def download(state: DownloadImageDialogState, asset: Asset) -> FrontendEvents:
        """Handle the download event for a base image."""
        state.asset = asset
        state.node = await state.get_var_value(ClusterDefaults.proxmox_node)
        return components.Dialog.open(DownloadImageDialog.dialog_id)

    @staticmethod
    @rx.event
    async def update(_: rx.State, asset: Asset) -> FrontendEvents:
        """Trigger the update process for a base image asset."""
        image = BaseImageManifest.load(name=asset.name)
        if image.metadata.build_date == asset.build_date:
            return rx.toast.info(f"{image.metadata.os} already up to date.")
        return [
            BaseImagesTable.update_in_background(image, asset),
            rx.toast.info(f"Updating {image.metadata.os}..."),
        ]

    @staticmethod
    @rx.event(background=True)
    async def update_in_background(_: rx.State, image: BaseImageManifest, asset: Asset) -> FrontendEvents:
        """Run the image update process in a background thread and update the UI upon completion."""
        await rx.run_in_thread(
            lambda: ProxmoxCompute().update_vendored_image(image=image, asset=asset),
        )
        return [
            BaseImagesTableState.cache_clear("available_images"),
            rx.toast.success(f"Successfully updated {image.metadata.os}!"),
        ]

    @classmethod
    def __table_row__(cls, asset: Asset) -> rx.Component:
        """Create and return the table row component."""
        manifest: rx.vars.ObjectVar[BaseImageManifest] = (
            BaseImagesTableState.existing.get(asset.name)
            .to(BaseImageManifest)
        )
        return rx.el.tr(
            rx.el.td(
                rx.el.div(
                    rx.text(asset.formatted_name),
                    rx.cond(
                        manifest.is_not_none(),
                        rx.text(manifest.spec.filename, class_name="text-sm text-gray-500"),
                        rx.text(asset.name, class_name="text-sm text-gray-500"),
                    ),
                    class_name="flex-col space-y-1 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.cond(
                    manifest.is_not_none(),
                    rx.text(f"{manifest.spec.node}"),
                    rx.text("-"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.cond(
                    manifest.is_not_none(),
                    rx.text(f"{manifest.spec.storage}"),
                    rx.text("-"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.cond(
                    manifest.is_not_none(),
                    rx.moment(manifest.metadata.download_date, local=True),
                    rx.text("-"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                components.Menu(
                    components.Buttons.Icon("ellipsis-vertical"),
                    components.Menu.Item(
                        "Create Custom Image",
                        on_click=CustomImageDialog.start_image_creation(manifest.spec.filename),
                    ),
                    components.Menu.Separator(),
                    rx.cond(
                        manifest.is_not_none(),
                        components.Menu.Item("Update", on_click=cls.update(asset)),
                        components.Menu.Item("Download", on_click=cls.download(asset)),
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
                            rx.el.th("OS", class_name=header_class),
                            rx.el.th("Node", class_name=header_class),
                            rx.el.th("Storage", class_name=header_class),
                            rx.el.th("Download Date", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(
                            BaseImagesTableState.available_images.values(),
                            lambda app: cls.__table_row__(app),
                        ),
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
            header=components.Card.Header(
                rx.el.div(
                    rx.el.h3("Base Images"),
                    rx.el.div(
                        components.Buttons.Icon(
                            "refresh-ccw",
                            on_click=BaseImagesTableState.cache_clear("available_images"),
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
    async def edit_image(state: CustomImageDialogState, name: str) -> FrontendEvents:
        """Edit a custom appliance by name and open the dialog."""
        state.edit_mode = True
        image = CustomImageManifest.load(name=name)
        return [
            CustomImageDialogState.load_image(image),
            components.Dialog.open(CustomImageDialog.dialog_id),
        ]

    @classmethod
    def __step_info__(cls, step: ScriptStep | FileStep, index: int) -> rx.Component:
        """Create a component displaying step information with index and type badge."""
        return rx.el.div(
            rx.text(f"{index + 1}. {step.name} ", rx.el.span(components.Badge(step.type, color_scheme="blue"))),
            class_name="w-fit p-2 flex-col space-y-2",
        )

    @classmethod
    def __table_row__(cls, image: CustomImageManifest) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                rx.el.div(
                    rx.text(image.metadata.name, class_name="text-base"),
                    rx.text(image.name, class_name="text-xs text-gray-500"),
                    class_name="flex-col space-y-1 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                image.spec.base_image,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.foreach(
                    rx.Var.create(image.spec.certificate_authorities).to(list[str]),
                    lambda cert: components.Badge(cert, color_scheme="blue"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300 space-x-1",
            ),
            rx.el.td(
                components.HoverCard(
                    rx.el.div(
                        rx.match(
                            image.metadata.status,
                            (
                                WorkflowStatus.SUCCEEDED,
                                components.Badge(image.metadata.status.capitalize(), color_scheme="green"),
                            ),
                            (
                                WorkflowStatus.FAILED,
                                components.Badge(image.metadata.status.capitalize(), color_scheme="red"),
                            ),
                            components.Badge(image.metadata.status.capitalize(), color_scheme="blue"),
                        ),
                    ),
                    rx.cond(
                        rx.Var.create(image.metadata.last_execution).is_none(),
                        rx.text("Not Ran"),
                        rx.moment(image.metadata.last_execution, local=True, from_now_during=1209600000),
                    ),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                components.HoverCard(
                    rx.text(rx.Var.create(image.spec.steps).to(list).length(), class_name="w-full pl-10"),
                    rx.foreach(image.spec.steps, lambda step, index: cls.__step_info__(step, index)),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.moment(image.metadata.created_on, local=True, from_now_during=1209600000),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                components.Menu(
                    components.Buttons.Icon("ellipsis-vertical"),
                    components.Menu.Item(
                        "Edit",
                        on_click=CustomImagesTable.edit_image(image.name),
                    ),
                    components.Menu.Item(
                        "Rerun Workflow",
                        on_click=CustomImageDialog.run_workflow(image.name),
                    ),
                    components.Menu.Separator(),
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
                            rx.el.th("Name", class_name=header_class),
                            rx.el.th("Base Image", class_name=header_class),
                            rx.el.th("Trusted CAs", class_name=header_class),
                            rx.el.th("Workflow Status", class_name=header_class),
                            rx.el.th("Workflow Steps", class_name=header_class),
                            rx.el.th("Date Created", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(CustomImagesTableState.custom_images, lambda app: cls.__table_row__(app)),
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
                    rx.el.h3("Custom Images", class_name="text-center"),
                    components.Buttons.Icon(
                        "refresh-ccw",
                        on_click=CustomImagesTableState.cache_clear("custom_images"),
                    ),
                    class_name="w-full flex justify-between items-center",
                ),
            ),
            class_name="w-full mt-6",
        )
