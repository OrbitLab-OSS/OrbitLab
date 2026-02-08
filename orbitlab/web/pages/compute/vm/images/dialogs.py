"""OrbitLab Image Dialogs."""

from collections.abc import AsyncGenerator
from typing import Final

import reflex as rx
from reflex.event import EventCallback, EventSpec

from orbitlab.clients.proxmox.compute.client import ProxmoxCompute
from orbitlab.clients.proxmox.compute.models import Asset
from orbitlab.clients.proxmox.compute_templates import ProxmoxComputeTemplates
from orbitlab.data_types import FrontendEvents, WorkflowStatus
from orbitlab.manifest.compute_templates.images import BaseImageManifest, CustomImageManifest
from orbitlab.web import components
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.utilities import EventGroup

from .models import CreateCustomImageForm
from .progress_panels import GeneralConfigurationPanel, ReviewPanel, WorkflowConfigurationPanel
from .states import BaseImagesTableState, CustomImageDialogState, CustomImagesTableState, DownloadImageDialogState


class DownloadImageDialog(EventGroup):
    """Dialog group for downloading vendored images to a selected node and storage."""

    dialog_id: Final = "download-vendored-image-dialog"
    form_id: Final = "download-vendored-image-form"

    @staticmethod
    @rx.event
    async def set_node(state: DownloadImageDialogState, node: str) -> None:
        """Set the selected node in the dialog state."""
        state.node = node

    @staticmethod
    @rx.event
    async def submit(state: DownloadImageDialogState, form: dict) -> FrontendEvents | None:
        """Handle the submission of the download image form."""
        if state.asset:
            default_storage = await state.get_var_value(ClusterDefaults.import_storage)
            storage: str = form.get("storage", default_storage)
            BaseImageManifest.create(storage=storage, node=state.node, asset=state.asset)
            return [
                components.Dialog.close(DownloadImageDialog.dialog_id),
                DownloadImageDialog.download(storage, state.asset),
                rx.toast.info(f"Downloading {state.os_name}"),
            ]
        return None

    @staticmethod
    @rx.event(background=True)
    async def download(state: DownloadImageDialogState, storage: str, asset: Asset) -> FrontendEvents:
        """Wait for image download task to complete and update state."""
        await rx.run_in_thread(lambda: ProxmoxCompute().download_vendored_image(storage=storage, asset=asset))
        async with state:
            state.reset()
        return [
            BaseImagesTableState.cache_clear("available_images"),
            rx.toast.success(f"Image {asset.formatted_name} download complete!"),
        ]

    @staticmethod
    @rx.event
    async def cancel(state: DownloadImageDialogState) -> FrontendEvents:
        """Handle the cancellation of the download image dialog."""
        state.reset()
        return components.Dialog.close(DownloadImageDialog.dialog_id)

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            f"Download {DownloadImageDialogState.os_name}",
            rx.el.div(
                rx.el.form(id=cls.form_id, on_submit=cls.submit),
                components.Select(
                    DownloadImageDialogState.nodes,
                    default_value=ClusterDefaults.proxmox_node,
                    placeholder="Select Node",
                    name="node",
                    required=True,
                    on_change=lambda node: cls.set_node(node),
                ),
                components.Select(
                    DownloadImageDialogState.import_storages,
                    default_value=ClusterDefaults.import_storage,
                    placeholder="Select Storage",
                    name="storage",
                    required=True,
                ),
                class_name="w-full flex-col space-y-2 items-center justify-center",
            ),
            rx.el.div(
                rx.el.div(),
                rx.el.div(
                    components.Buttons.Secondary("Cancel", on_click=cls.cancel),
                    components.Buttons.Primary("Download", form=cls.form_id),
                    class_name="w-full flex space-x-2",
                ),
                class_name="w-full flex justify-between mt-10",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[25vw] w-fit max-h-[30vh] h-fit",
        )


class CustomImageDialog(EventGroup):
    """Dialog group for creating and configuring custom VM images in OrbitLab."""

    @staticmethod
    @rx.event
    async def start_image_creation(state: CustomImageDialogState, base_image: str) -> FrontendEvents:
        """Initialize image creation from a base image and open the dialog."""
        state.form_data["base_image"] = base_image
        state.form_data["node"] = await state.get_var_value(ClusterDefaults.proxmox_node)
        return components.Dialog.open(CustomImageDialog.dialog_id)

    @staticmethod
    @rx.event
    async def validate_general(state: CustomImageDialogState, form: dict) -> FrontendEvents:
        """Update the form data with new values and proceed to the next step in the progress panel."""
        if not state.edit_mode:
            name = form["name"]
            if name in CustomImageManifest.get_existing():
                return rx.toast.error(f"Image with name '{name}' already exists.")
        form["memory"] = int(form["memory"])
        form["cores"] = int(form["cores"])
        form["disk_size"] = int(form["disk_size"])
        state.form_data.update(form)
        return components.ProgressPanels.next(CustomImageDialog.progress_id)

    @staticmethod
    @rx.event
    async def validate_wf_steps(state: CustomImageDialogState, _: dict) -> FrontendEvents:
        """Validate all workflow steps in the image configuration."""
        steps = []
        for step in state.step_order:
            if not state.steps_config[step["id"]]:
                return rx.toast.error("All steps must be configured.")
            if error := state.steps_config[step["id"]].validate():
                step_name = state.steps_config[step["id"]].name or ""
                return rx.toast.error(f"Step {step_name}: {error}")
            steps.append(state.steps_config[step["id"]])
        state.form_data["workflow_steps"] = steps
        return components.ProgressPanels.next(CustomImageDialog.progress_id)

    @staticmethod
    @rx.event
    async def create_image(state: CustomImageDialogState, form: dict) -> FrontendEvents:
        """Create the custom image with the configured settings and workflow steps."""
        state.form_data.update(form)
        if state.edit_mode:
            manifest = CustomImageManifest.load(name=state.image_id)
            manifest.update(form_data=CreateCustomImageForm.model_validate(state.form_data))
        else:
            manifest = CustomImageManifest.create(
                form_data=CreateCustomImageForm.model_validate(state.form_data),
            )
        return [
            CustomImageDialog.reset,
            CustomImageDialog.run_workflow(manifest.name),
        ]

    @staticmethod
    @rx.event(background=True)
    async def run_workflow(_: rx.State, name: str) -> AsyncGenerator[EventSpec | EventCallback]:
        """Run the workflow for the specified custom image by name."""
        manifest = CustomImageManifest.load(name=name)
        manifest.set_workflow_status(status=WorkflowStatus.PENDING)
        yield CustomImagesTableState.cache_clear("custom_images")
        yield rx.toast.info(f"Starting {manifest.metadata.name} workflow...")
        status: WorkflowStatus = await rx.run_in_thread(
            lambda: ProxmoxComputeTemplates().run_workflow(manifest=manifest),
        )
        manifest.set_workflow_status(status=status)
        if status == WorkflowStatus.SUCCEEDED:
            yield rx.toast.success(f"Image {name} workflow succeeded!")
        else:
            yield rx.toast.error(f"Image {name} workflow failed.")
        yield CustomImagesTableState.cache_clear("custom_images")

    @staticmethod
    @rx.event
    async def reset(state: CustomImageDialogState) -> FrontendEvents:
        """Cancel the image creation process and reset the dialog state."""
        state.reset()
        return [
            components.Dialog.close(CustomImageDialog.dialog_id),
            components.ProgressPanels.reset(CustomImageDialog.progress_id),
        ]

    dialog_id: Final = "create-image-dialog"
    progress_id: Final = "create-image-progress-panels"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            "Create Custom Image",
            components.ProgressPanels(
                components.ProgressPanels.Step(
                    "General Configuration",
                    GeneralConfigurationPanel(),
                    validate=cls.validate_general,
                ),
                components.ProgressPanels.Step(
                    "Workflow Steps",
                    WorkflowConfigurationPanel(),
                    validate=cls.validate_wf_steps,
                ),
                components.ProgressPanels.Step(
                    "Review & Verify",
                    ReviewPanel(),
                    validate=cls.create_image,
                ),
                cancel_button=components.Buttons.Secondary("Cancel", on_click=cls.reset),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )
