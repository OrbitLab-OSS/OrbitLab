"""OrbitLab Image States."""


import json
from typing import Literal

import reflex as rx

from orbitlab.data_types import StorageContentType
from orbitlab.manifest.compute_templates import CustomImageManifest
from orbitlab.manifest.compute_templates.images import BaseImageManifest
from orbitlab.manifest.compute_templates.workflow_models import FileConfig, WorkflowStep
from orbitlab.manifest.nodes import NodeManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.proxmox import ProxmoxComputeTemplates
from orbitlab.proxmox.compute.models import VendoredImage
from orbitlab.web import components
from orbitlab.web.utilities import CacheBuster, get_redis


class BaseImagesTableState(CacheBuster, rx.State):
    """State management for the base images table, handling available and existing images."""

    nodes: rx.Field[list[str]] = rx.field(default_factory=NodeManifest.get_existing)

    @rx.var(deps=["_cached_available_images"])
    def available_images(self) -> list[BaseImageManifest]:
        """Return a dictionary of available images keyed by their name."""
        return [BaseImageManifest.load(name=name) for name in BaseImageManifest.get_existing()]


class DownloadImageDialogState(rx.State):
    """State for managing the download image dialog, including selected asset and node."""

    vendored_images: rx.Field[list[VendoredImage]] = rx.field(default_factory=list)
    nodes: rx.Field[list[str]] = rx.field(default_factory=NodeManifest.get_existing)
    node: rx.Field[str] = rx.field(default="")

    @rx.var
    def available_images(self) -> dict[str, str]:
        existing = [BaseImageManifest.load(name=name).metadata.os for name in BaseImageManifest.get_existing()]
        return {img.formatted_name: img.filename for img in self.vendored_images if img.formatted_name not in existing}

    @rx.var
    def import_storages(self) -> list[str]:
        """Return a list of import storages available for the selected node."""
        if self.node:
            return NodeManifest.load(name=self.node).list_storages(content_type=StorageContentType.IMPORT)
        return []


class CustomImageDialogState(rx.State):
    """State for managing the custom image dialog."""

    edit_mode: rx.Field[bool] = rx.field(default=False)

    image_id: rx.Field[str] = rx.field(default="")
    memory_gb: rx.Field[int] = rx.field(default=2)
    cores: rx.Field[int] = rx.field(default=2)
    disk_size: rx.Field[int] = rx.field(default=8)

    form_data: rx.Field[dict] = rx.field(default_factory=dict)
    step_order: rx.Field[list[components.SortableItem]] = rx.field(default_factory=list)
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
    def node(self) -> str:
        """Get the selected node name from form data."""
        return self.form_data.get("node", "")

    @rx.var
    def name(self) -> str:
        """Get the image name from form data."""
        return self.form_data.get("name", "")

    @rx.var
    def base_image(self) -> str:
        """Get the base image name from form data."""
        return self.form_data.get("base_image", "")

    @rx.var
    def image_store(self) -> str:
        """Get the image storage location from form data."""
        return self.form_data.get("image_store", "")

    @rx.var
    def disk_store(self) -> str:
        """Get the temporary disk storage location from form data."""
        return self.form_data.get("disk_store", "")

    @rx.var
    def sector(self) -> str:
        """Get the selected sector name from form data."""
        return self.form_data.get("sector", "")

    @rx.var
    def root_certs(self) -> list[str]:
        """Get the selected root CAs from form data."""
        # certs = self.form_data.get("certificate_authorities") or "[]"
        # return json.loads(certs)
        return []

    @rx.var
    def step_names_in_order(self) -> list[str]:
        """Get the names of workflow steps in their configured order."""
        return [self.steps_config[step["id"]].name for step in self.step_order]

    @rx.var
    def base_images(self) -> dict[str, str]:
        return {
            f"{base.metadata.os} ({base.name})": base.name
            for base in [BaseImageManifest.load(name=name) for name in BaseImageManifest.get_existing()]
        }

    @rx.var
    def available_image_stores(self) -> list[str]:
        """Return a list of available image storage locations for the selected node."""
        if self.node:
            return ProxmoxComputeTemplates().list_storages_for_node(
                node=self.node, content_type=StorageContentType.IMPORT,
            )
        return []

    @rx.var
    def available_disk_stores(self) -> list[str]:
        """Return a list of available VM disk storage locations for the selected node."""
        if self.node:
            return ProxmoxComputeTemplates().list_storages_for_node(
                node=self.node, content_type=StorageContentType.IMAGES,
            )
        return []

    @rx.var(cache=False)
    def available_sectors(self) -> dict[str, str]:
        """Get a mapping of sector display names to sector names."""
        return {
            f"{sector.name} ({sector.spec.cidr_block})": sector.name
            for sector in [SectorManifest.load(name=name) for name in SectorManifest.get_existing()]
        }

    @rx.event
    async def load_image(self, image: CustomImageManifest) -> None:
        """Load the configuration from a CustomImageManifest into the dialog state."""
        self.image_id = image.name
        self.memory_gb = image.spec.memory
        self.cores = image.spec.cores
        self.disk_size = image.spec.disk_size
        self.form_data = {
            "name": image.metadata.name,
            "base_image": image.spec.base_image,
            "node": image.spec.node,
            "disk_store": image.spec.disk_storage,
            "image_store": image.spec.image_storage,
            "sector": image.spec.sector,
        }
        for index, step in enumerate(image.spec.steps):
            self.step_order.append({"id": index})
            self.steps_config[index] = WorkflowStep.model_validate(step.model_dump())


async def get_workflow_status(manifest_name: str) -> str:
    """Retrieve a value from Redis for a given manifest and key."""
    redis = get_redis()
    status = await redis.hget(name=f"ol:image:{manifest_name}", key="status")
    if isinstance(status, bytes):
        return status.decode()
    return "Never Ran"


class CustomImagesTableState(CacheBuster, rx.State):
    """State management for the custom images table."""
    workflow_to_view: str = ""

    @rx.var(deps=["_cached_custom_images"])
    def custom_images(self) -> list[CustomImageManifest]:
        """Return a list of loaded CustomImageManifest instances for existing custom images."""
        return [CustomImageManifest.load(name=name) for name in CustomImageManifest.get_existing()]

    @rx.var(deps=["_cached_logs"])
    async def logs(self) -> str:
        """Workflow logs."""
        if self.workflow_to_view:
            redis = get_redis()
            logs: bytes = await redis.hget(name=f"ol:image:{self.workflow_to_view}", key="logs")
            return logs.decode()
        return ""

    @rx.var
    async def workflow_states(self) -> dict[str, str]:
        """Mapping of manifest names to Workflow States."""
        return {
            manifest.name: await get_workflow_status(manifest_name=manifest.name)
            for manifest in self.custom_images
        }


class DeleteImageDialogState(rx.State):
    """State for managing the delete image dialog, including confirmation."""

    name: str = ""
    image_type: Literal["base", "custom"] = "base"
    confirmation: str = ""

    @rx.var
    def delete_disabled(self) -> bool:
        """Return True if the delete action should be disabled (name and confirmation do not match)."""
        return self.name != self.confirmation
