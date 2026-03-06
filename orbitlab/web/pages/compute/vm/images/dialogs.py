"""OrbitLab Image Dialogs."""

from collections.abc import AsyncGenerator
from typing import Final

import reflex as rx
from reflex.event import EventCallback, EventSpec

from orbitlab.data_types import FrontendEvents
from orbitlab.manifest.compute_templates.images import BaseImageManifest, CustomImageManifest
from orbitlab.proxmox.compute_templates import ProxmoxComputeTemplates
from orbitlab.web import components
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.utilities import EventGroup, get_worker

from .models import CreateCustomImageForm
from .progress_panels import GeneralConfigurationPanel, ReviewPanel, WorkflowConfigurationPanel
from .states import (
    CustomImageDialogState,
    CustomImagesTableState,
    DeleteImageDialogState,
    DownloadImageDialogState,
)


class DownloadImageDialog(EventGroup):
    """Dialog group for downloading vendored images to a selected node and storage."""

    @staticmethod
    @rx.event
    async def open(state: DownloadImageDialogState) -> None:
        """Set the selected node in the dialog state."""
        state.vendored_images = ProxmoxComputeTemplates().get_vendored_images().images
        state.node = await state.get_var_value(ClusterDefaults.proxmox_node)
        return components.Dialog.open(DownloadImageDialog.dialog_id)

    @staticmethod
    @rx.event
    async def set_node(state: DownloadImageDialogState, node: str) -> None:
        """Set the selected node in the dialog state."""
        state.node = node

    @staticmethod
    @rx.event
    async def submit(state: DownloadImageDialogState, form: dict) -> FrontendEvents | None:
        """Handle the submission of the download image form."""
        storage: str = form["storage"]
        filename = form["image"]
        image = next(iter(img for img in state.vendored_images if img.filename == filename))
        manifest = BaseImageManifest.create(storage=storage, node=state.node, image=image)
        worker = get_worker()
        error = await worker.create_workflow(
            name="image.download",
            version="v1",
            payload={"manifest": manifest.name},
        )
        if error:
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Downloading {manifest.spec.filename}..."),
            DownloadImageDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: DownloadImageDialogState) -> FrontendEvents:
        """Handle the cancellation of the download image dialog."""
        state.reset()
        return components.Dialog.close(DownloadImageDialog.dialog_id)

    dialog_id: Final = "download-vendored-image-dialog"
    form_id: Final = "download-vendored-image-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            "Download Vendored Image",
            rx.el.div(
                rx.el.form(
                    components.Select(
                        DownloadImageDialogState.available_images,
                        placeholder="Select Available Image",
                        name="image",
                        form=cls.form_id,
                        required=True,
                    ),
                    components.Select(
                        DownloadImageDialogState.nodes,
                        default_value=ClusterDefaults.proxmox_node,
                        placeholder="Select Node",
                        required=True,
                        on_change=lambda node: cls.set_node(node),
                    ),
                    components.Select(
                        DownloadImageDialogState.import_storages,
                        default_value=ClusterDefaults.import_storage,
                        placeholder="Select Storage",
                        name="storage",
                        form=cls.form_id,
                        required=True,
                    ),
                    class_name="w-full flex-col space-y-4",
                    id=cls.form_id,
                    on_submit=cls.submit,
                ),
                class_name="w-full flex-col space-y-2 items-center justify-center",
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.close),
                components.Buttons.Primary("Download", form=cls.form_id),
                class_name="w-full flex space-x-2 items-center, justify-end mt-8",
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
        state.form_data["image_store"] = await state.get_var_value(ClusterDefaults.import_storage)
        state.form_data["disk_store"] = await state.get_var_value(ClusterDefaults.images_storage)
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
            CustomImageDialog.close,
            CustomImageDialog.run_workflow(manifest.name),
        ]

    @staticmethod
    @rx.event
    async def run_workflow(_: rx.State, name: str) -> AsyncGenerator[EventSpec | EventCallback]:
        """Run the workflow for the specified custom image by name."""
        worker = get_worker()
        error = await worker.create_workflow(
            name="image.custom",
            version="v1",
            payload={"manifest": name},
        )
        if error:
            return rx.toast.error(error)
        return [
            CustomImageDialog.close,
            rx.toast.info(f"Running {name} worfklow..."),
        ]

    @staticmethod
    @rx.event
    async def close(state: CustomImageDialogState) -> FrontendEvents:
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
                cancel_button=components.Buttons.Secondary("Cancel", on_click=cls.close),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )


class DeleteImageDialog(EventGroup):
    """Delete a VM Image."""

    @staticmethod
    @rx.event
    async def confirm(state: DeleteImageDialogState, name: str) -> FrontendEvents:
        """Set image name to delete and open dialog."""
        state.reset()
        state.name = name
        if name in CustomImageManifest.get_existing():
            state.image_type = "custom"
        else:
            state.image_type = "base"
        return components.Dialog.open(DeleteImageDialog.dialog_id)

    @staticmethod
    @rx.event
    async def update_confirmation(state: DeleteImageDialogState, value: str) -> None:
        """Update the confirmation input text value."""
        state.confirmation = value

    @staticmethod
    @rx.event
    async def delete(state: DeleteImageDialogState) -> FrontendEvents:
        """Delete a custom appliance from Proxmox and remove its manifest."""
        worker = get_worker()
        error = await worker.create_workflow(
            name="image.delete",
            version="v1",
            payload={"manifest": state.name, "image_type": state.image_type},
        )
        if error:
            return rx.toast.error(error)
        return [
            DeleteImageDialog.close,
            rx.toast.info(f"Deleting {state.name}..."),
        ]

    @staticmethod
    @rx.event
    async def close(state: DeleteImageDialogState) -> FrontendEvents:
        """Cancel custom appliance deletion and close the dialog."""
        state.reset()
        return components.Dialog.close(DeleteImageDialog.dialog_id)

    dialog_id: Final = "confirm-delete-image-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return components.Dialog(
            f"Delete {DeleteImageDialogState.name}",
            rx.el.div(
                rx.text(
                    "You are about to delete custom LXC appliance '",
                    rx.el.span(DeleteImageDialogState.name, class_name="font-bold"),
                    rx.el.span(
                        """'. This will delete the manifest and the appliance from Proxmox Storage. Any existing
                        compute created from this appliance will not be affected.
                        """,
                    ),
                ),
                rx.text("If you are sure you want to delete this appliance, type its name below."),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            components.Input(
                placeholder=DeleteImageDialogState.name,
                on_change=cls.update_confirmation,
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.close),
                components.Buttons.Primary(
                    "Delete",
                    disabled=DeleteImageDialogState.delete_disabled,
                    on_click=cls.delete,
                ),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )


class WorkflowLogsViewDialog(EventGroup):
    """View custom appliance workflow logs."""

    @staticmethod
    @rx.event
    async def view_workflow_logs(state: CustomImagesTableState, name: str) -> FrontendEvents:
        """Set the workflow to view and open the dialog."""
        state.workflow_to_view = name
        return components.Dialog.open(WorkflowLogsViewDialog.dialog_id)

    @staticmethod
    @rx.event
    async def close(state: CustomImagesTableState) -> FrontendEvents:
        """Close the dialog."""
        state.reset()
        return components.Dialog.close(WorkflowLogsViewDialog.dialog_id)

    dialog_id: Final = "image-workflow-logs-view-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return components.Dialog(
            f"{CustomImagesTableState.workflow_to_view} Workflow Logs",
            rx.el.div(
                rx.code_block(
                    language="shell-session",
                    code=CustomImagesTableState.logs,
                    code_tag_props={"style": {"whiteSpace": "pre-wrap"}},
                    show_line_numbers=True,
                ),
                class_name="w-full h-full overflow-auto",
            ),
            rx.el.div(
                components.Buttons.Secondary("Close", on_click=cls.close),
                class_name="w-full flex justify-end space-x-4 my-4",
            ),
            dialog_id=cls.dialog_id,
        )
