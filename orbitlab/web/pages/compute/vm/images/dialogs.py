"""OrbitLab Image Dialogs."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Final

import reflex as rx
from reflex.event import EventCallback, EventSpec

from orbitlab.data_types import FrontendEvents, StorageContentType, TemplateWorkflowStatus
from orbitlab.proxmox.compute_templates import ProxmoxComputeTemplates
from orbitlab.redis.clients import ImagesClient
from orbitlab.redis.models import BaseImageConfig, CustomImageConfig
from orbitlab.web import tailwind
from orbitlab.web.global_state import SelectOptions, SelectionDefaults
from orbitlab.web.utilities import EventGroup, create_workflow, get_redis_value

from .progress_panels import GeneralConfigurationPanel, ReviewPanel, WorkflowConfigurationPanel
from .states import (
    CustomImageDialogState,
    ImageWorkflowLogsViewDialogState,
    DeleteImageDialogState,
    DownloadImageDialogState,
)


class DownloadImageDialog(EventGroup):
    """Dialog group for downloading vendored images to a selected node and storage."""

    @staticmethod
    @rx.event
    async def open(state: DownloadImageDialogState) -> None:
        """Set the selected node in the dialog state."""
        state.vendored_images = {
            image.filename: image for image in (await ProxmoxComputeTemplates().get_vendored_images()).images
        }
        state.node = await state.get_var_value(SelectionDefaults.default_node)
        return tailwind.Dialog.open(DownloadImageDialog.dialog_id)

    @staticmethod
    @rx.event
    async def set_node(state: DownloadImageDialogState, node: str) -> None:
        """Set the selected node in the dialog state."""
        state.node = node

    @staticmethod
    @rx.event
    async def submit(state: DownloadImageDialogState, form: dict) -> FrontendEvents | None:
        """Handle the submission of the download image form."""
        image = state.vendored_images[form["image"]]
        client = ImagesClient()
        base_image = await client.set_image(
            image_type="base",
            config=BaseImageConfig(
                id=await client.generate_image_id(image_type="base"),
                node=state.node,
                filename=image.filename,
                storage=form["storage"],
                checksum_algorithm=image.checksum_algorithm,
                checksum=image.checksum,
                os=image.formatted_name,
                build_date=image.build_date,
                download_url=image.browser_download_url,
            ),
        )
        if error := await create_workflow(name="image.download", version="v1", payload={"id": base_image.config.id}):
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Downloading {image.filename}..."),
            DownloadImageDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: DownloadImageDialogState) -> FrontendEvents:
        """Handle the cancellation of the download image dialog."""
        state.reset()
        return tailwind.Dialog.close(DownloadImageDialog.dialog_id)

    dialog_id: Final = "download-vendored-image-dialog"
    form_id: Final = "download-vendored-image-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        node_storage_options = SelectOptions.node_storage_options.get(
            DownloadImageDialogState.node, default={},
        ).to(dict[StorageContentType, list[str]])
        import_storage_options = node_storage_options.get(StorageContentType.IMPORT, []).to(list[str])
        return tailwind.Dialog(
            "Download Vendored Image",
            rx.el.div(
                rx.el.form(
                    tailwind.Select(
                        DownloadImageDialogState.vendored_image_options,
                        placeholder="Select Available Image",
                        name="image",
                        form=cls.form_id,
                        required=True,
                    ),
                    tailwind.Select(
                        SelectOptions.node_options,
                        default_value=SelectionDefaults.default_node,
                        placeholder="Select Node",
                        required=True,
                        on_change=lambda node: cls.set_node(node),
                    ),
                    tailwind.Select(
                        import_storage_options,
                        default_value=SelectionDefaults.default_import_storage,
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
                tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                tailwind.Buttons.Primary("Download", form=cls.form_id),
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
        state.form_data["node"] = await state.get_var_value(SelectionDefaults.default_node)
        state.form_data["image_store"] = await state.get_var_value(SelectionDefaults.default_import_storage)
        state.form_data["disk_store"] = await state.get_var_value(SelectionDefaults.default_images_storage)
        return tailwind.Dialog.open(CustomImageDialog.dialog_id)

    @staticmethod
    @rx.event
    async def validate_general(state: CustomImageDialogState, form: dict) -> FrontendEvents:
        """Update the form data with new values and proceed to the next step in the progress panel."""
        existing = await state.get_var_value(SelectOptions.custom_image_options)
        if not state.edit_mode:
            name = form["name"]
            if name in existing.values():
                return rx.toast.error(f"Image with name '{name}' already exists.")
        form["memory"] = int(form["memory"])
        form["cores"] = int(form["cores"])
        form["disk_size"] = int(form["disk_size"])
        state.form_data.update(form)
        return tailwind.ProgressPanels.next(CustomImageDialog.progress_id)

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
        return tailwind.ProgressPanels.next(CustomImageDialog.progress_id)

    @staticmethod
    @rx.event
    async def create_image(state: CustomImageDialogState, form: dict) -> FrontendEvents:
        """Create the custom image with the configured settings and workflow steps."""
        state.form_data.update(form)
        client = ImagesClient()
        base_volume_id = await client.get_volume_id(id=state.form_data["base_image"])
        custom_image = await client.set_image(
            image_type="custom",
            config=CustomImageConfig(
                id=state.image_id or await client.generate_image_id(image_type="custom"),
                name=state.form_data["name"],
                base_image_id=state.form_data["base_image"],
                base_volume_id=base_volume_id,
                node=state.form_data["node"],
                disk_storage=state.form_data["disk_store"],
                disk_size=int(state.form_data["disk_size"]),
                image_storage=state.form_data["image_store"],
                memory=int(state.form_data["memory"]),
                cores=int(state.form_data["cores"]),
                sector=state.form_data["sector"],
                steps=state.form_data["workflow_steps"]
            )
        )
        return [
            CustomImageDialog.close,
            CustomImageDialog.run_workflow(custom_image.config.id),
        ]

    @staticmethod
    @rx.event
    async def run_workflow(_: rx.State, image_id: str) -> AsyncGenerator[EventSpec | EventCallback]:
        """Run the workflow for the specified custom image."""
        if error := await create_workflow(name="image.custom", version="v1", payload={"id": image_id}):
            return rx.toast.error(error)
        return [
            CustomImageDialog.close,
            rx.toast.info(f"Running {image_id} worfklow..."),
            WorkflowLogsViewDialog.open(image_id),
        ]

    @staticmethod
    @rx.event
    async def close(state: CustomImageDialogState) -> FrontendEvents:
        """Cancel the image creation process and reset the dialog state."""
        state.reset()
        return [
            tailwind.Dialog.close(CustomImageDialog.dialog_id),
            tailwind.ProgressPanels.reset(CustomImageDialog.progress_id),
        ]

    dialog_id: Final = "create-image-dialog"
    progress_id: Final = "create-image-progress-panels"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
            "Create Custom Image",
            tailwind.ProgressPanels(
                tailwind.ProgressPanels.Step(
                    "General Configuration",
                    GeneralConfigurationPanel(),
                    validate=cls.validate_general,
                ),
                tailwind.ProgressPanels.Step(
                    "Workflow Steps",
                    WorkflowConfigurationPanel(),
                    validate=cls.validate_wf_steps,
                ),
                tailwind.ProgressPanels.Step(
                    "Review & Verify",
                    ReviewPanel(),
                    validate=cls.create_image,
                ),
                cancel_button=tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )


class DeleteImageDialog(EventGroup):
    """Delete a VM Image."""

    @staticmethod
    @rx.event
    async def confirm(state: DeleteImageDialogState, image_id: str) -> FrontendEvents:
        """Set image name to delete and open dialog."""
        state.reset()
        state.image_id = image_id
        custom_images = await state.get_var_value(SelectOptions.custom_image_options)
        if image_id in custom_images.values():
            state.image_type = "custom"
        else:
            state.image_type = "base"
        return tailwind.Dialog.open(DeleteImageDialog.dialog_id)

    @staticmethod
    @rx.event
    async def update_confirmation(state: DeleteImageDialogState, value: str) -> None:
        """Update the confirmation input text value."""
        state.confirmation = value

    @staticmethod
    @rx.event
    async def delete(state: DeleteImageDialogState) -> FrontendEvents:
        """Delete a custom appliance from Proxmox and remove its manifest."""
        payload = {"id": state.image_id, "image_type": state.image_type}
        if error := await create_workflow(name="image.delete", version="v1", payload=payload):
            return rx.toast.error(error)
        return [
            DeleteImageDialog.close,
            rx.toast.info(f"Deleting {state.image_id}..."),
        ]

    @staticmethod
    @rx.event
    async def close(state: DeleteImageDialogState) -> FrontendEvents:
        """Cancel custom appliance deletion and close the dialog."""
        state.reset()
        return tailwind.Dialog.close(DeleteImageDialog.dialog_id)

    dialog_id: Final = "confirm-delete-image-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return tailwind.Dialog(
            f"Delete {DeleteImageDialogState.image_id}",
            rx.el.div(
                rx.text(
                    "You are about to delete custom LXC appliance '",
                    rx.el.span(DeleteImageDialogState.image_id, class_name="font-bold"),
                    rx.el.span(
                        """'. This will delete the manifest and the appliance from Proxmox Storage. Any existing
                        compute created from this appliance will not be affected.
                        """,
                    ),
                ),
                rx.text("If you are sure you want to delete this appliance, type its name below."),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            tailwind.Input(
                placeholder=DeleteImageDialogState.image_id,
                on_change=cls.update_confirmation,
            ),
            rx.el.div(
                tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                tailwind.Buttons.Primary(
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
    @rx.event(background=True)
    async def refresh_logs(state: ImageWorkflowLogsViewDialogState) -> FrontendEvents | None:
        if state.view_workflow:
            while state.countdown_refresh_seconds != 0:
                async with state:
                    state.countdown_refresh_seconds -= 1
                await asyncio.sleep(1)
            async with state:
                state.logs = await get_redis_value(name=f"ol:image:{state.view_workflow}", key="logs")
                state.countdown_refresh_seconds = 5
            status = await ImagesClient().get_workflow_status(id=state.view_workflow)
            if status not in (TemplateWorkflowStatus.FAILED, TemplateWorkflowStatus.SUCCEEDED):
                state.workflow_running = True
                return [
                    WorkflowLogsViewDialog.refresh_logs,
                    rx.call_script(
                        "document.getElementById('custom-vm-workflow-logs').scrollIntoView({ behavior: 'smooth', block: 'end' });"
                    ),
                ]
            state.workflow_running = False
            return rx.call_script(
                "document.getElementById('custom-vm-workflow-logs').scrollIntoView({ behavior: 'smooth', block: 'end' });"
            )

    @staticmethod
    @rx.event
    async def open(state: ImageWorkflowLogsViewDialogState, name: str) -> FrontendEvents:
        """Set the workflow to view and open the dialog."""
        state.view_workflow = name
        return [
            WorkflowLogsViewDialog.refresh_logs,
            tailwind.Dialog.open(WorkflowLogsViewDialog.dialog_id)
        ]

    @staticmethod
    @rx.event
    async def close(state: ImageWorkflowLogsViewDialogState) -> FrontendEvents:
        """Close the dialog."""
        state.view_workflow = ""
        state.workflow_running = False
        state.logs = ""
        state.countdown_refresh_seconds = 5
        return tailwind.Dialog.close(WorkflowLogsViewDialog.dialog_id)

    dialog_id: Final = "image-workflow-logs-view-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return tailwind.Dialog(
            f"{ImageWorkflowLogsViewDialogState.view_workflow} Workflow Logs",
            rx.el.div(
                rx.cond(
                    ImageWorkflowLogsViewDialogState.logs != "",
                    rx.code_block(
                        language="log",
                        code=ImageWorkflowLogsViewDialogState.logs,
                        code_tag_props={"style": {"whiteSpace": "pre-wrap"}},
                        show_line_numbers=False,
                        id=rx.Var.create("custom-vm-workflow-logs"),
                    ),
                    rx.el.div(
                        tailwind.OrbitLabLogo(animated=True),
                        class_name="w-full h-full flex items-center justify-center"
                    ),
                ),
                class_name="w-full h-full overflow-auto",
            ),
            rx.el.div(
                tailwind.Buttons.Secondary(
                    rx.el.div(
                        "Close",
                        rx.cond(
                            ImageWorkflowLogsViewDialogState.workflow_running,
                            rx.progress(value=ImageWorkflowLogsViewDialogState.countdown_refresh_seconds, max=5),
                            rx.fragment(),
                        )
                    ),
                    on_click=cls.close,
                ),
                class_name="w-full flex justify-end space-x-4 my-4",
            ),
            dialog_id=cls.dialog_id,
        )
