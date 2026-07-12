"""OrbitLab Image States."""

from typing import Literal

import reflex as rx

from orbitlab.proxmox.models import VendoredImage
from orbitlab.redis.clients import ImagesClient
from orbitlab.web.tailwind.sortable import SortableItem
from orbitlab.web.global_state import OrbitLabState
from orbitlab.worker.workflows.models import FileConfig, WorkflowStep


class ImageWorkflowLogsViewDialogState(OrbitLabState):
    """State management for the custom images table."""
    
    view_workflow: rx.Field[str] = rx.field(default="")
    workflow_running: rx.Field[bool] = rx.field(default=False)
    logs: rx.Field[str] = rx.field(default="")
    countdown_refresh_seconds: rx.Field[int] = rx.field(default=5)


class DownloadImageDialogState(rx.State):
    """State for managing the download image dialog, including selected asset and node."""

    vendored_images: rx.Field[dict[str, VendoredImage]] = rx.field(default_factory=dict)
    node: rx.Field[str] = rx.field(default="")
    
    @rx.var
    def vendored_image_options(self) -> dict[str, str]:
        return {image.os: image.filename for image in self.vendored_images.values()}


class CustomImageDialogState(rx.State):
    """State for managing the custom image dialog."""

    edit_mode: rx.Field[bool] = rx.field(default=False)
    image_id: rx.Field[str] = rx.field(default="")
    form_data: rx.Field[dict] = rx.field(default_factory=dict)
    step_order: rx.Field[list[SortableItem]] = rx.field(default_factory=list)
    steps_config: rx.Field[dict[int, WorkflowStep]] = rx.field(default_factory=dict)
    
    uploading: rx.Field[bool] = rx.field(default=False)
    upload_progress: rx.Field[int] = rx.field(default=0)
    script_value: rx.Field[str] = rx.field(default="")
    default_script_value: rx.Field[str] = rx.field(default="")
    files_data: rx.Field[list[FileConfig] | None] = rx.field(default=None)

    @rx.var
    def dialog_title(self) -> str:
        """Return the dialog title based on whether edit mode is enabled."""
        if self.edit_mode:
            return f"Edit Image: {self.image_id}"
        return "Create Custom Image"

    @rx.var
    def step_names_in_order(self) -> list[str]:
        """Get the names of workflow steps in their configured order."""
        return [self.steps_config[step["id"]].name for step in self.step_order]

    @rx.var
    def workflow_steps(self) -> list[WorkflowStep]:
        return [self.steps_config[step["id"]] for step in self.step_order]

    @rx.event
    async def load_image(self, image_id: str) -> None:
        """Load the configuration from a CustomImageManifest into the dialog state."""
        image = await ImagesClient().get_image(image_type="custom", id=image_id)
        self.image_id = image.config.id
        self.form_data = {
            "id": image.config.id,
            "name": image.config.name,
            "base_image": image.config.base_image_id,
            "node": image.config.node,
            "disk_store": image.config.disk_storage,
            "image_store": image.config.storage,
            "sector": image.config.sector,
            "memory": image.config.memory,
            "cores": image.config.cores,
            "disk_size": image.config.disk_size,
        }
        for index, step in enumerate(image.config.steps):
            self.step_order.append({"id": index})
            self.steps_config[index] = WorkflowStep.model_validate(step.model_dump())


class DeleteImageDialogState(rx.State):
    """State for managing the delete image dialog, including confirmation."""

    image_id: str = ""
    image_type: Literal["base", "custom"] = "base"
    confirmation: str = ""

    @rx.var
    def delete_disabled(self) -> bool:
        """Return True if the delete action should be disabled (name and confirmation do not match)."""
        return self.image_id != self.confirmation
