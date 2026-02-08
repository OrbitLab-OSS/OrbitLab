"""OrbitLab Image States."""


import json

import reflex as rx

from orbitlab.clients.proxmox.compute.client import ProxmoxCompute
from orbitlab.clients.proxmox.compute.models import Asset
from orbitlab.data_types import StorageContentType
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.compute_templates import CustomImageManifest
from orbitlab.manifest.compute_templates.images import BaseImageManifest
from orbitlab.manifest.compute_templates.workflow_models import FileConfig, WorkflowStep
from orbitlab.manifest.nodes import NodeManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.web import components
from orbitlab.web.utilities import CacheBuster


class BaseImagesTableState(CacheBuster, rx.State):
    """State management for the base images table, handling available and existing images."""

    nodes: rx.Field[list[str]] = rx.field(default_factory=NodeManifest.get_existing)

    @rx.var(deps=["_cached_available_images"])
    def available_images(self) -> dict[str, Asset]:
        """Return a dictionary of available images keyed by their name."""
        return {asset.name: asset for asset in ProxmoxCompute.get_vendored_images().list_images()}

    @rx.var
    def existing(self) -> dict[str, BaseImageManifest | None]:
        """Return a dictionary mapping image names to their loaded BaseImageManifest or None if not present."""
        _existing = BaseImageManifest.get_existing()
        return {
            name: BaseImageManifest.load(name=name)
            if name in _existing else None for name in self.available_images
        }


class DownloadImageDialogState(rx.State):
    """State for managing the download image dialog, including selected asset and node."""

    asset: rx.Field[Asset | None] = rx.field(default=None)
    node: rx.Field[str] = rx.field(default="")

    @rx.var
    def os_name(self) -> str:
        """Return the formatted OS name of the selected asset, or an empty string if no asset is selected."""
        if self.asset:
            return self.asset.formatted_name
        return ""

    @rx.var
    def nodes(self) -> list[str]:
        """Return a list of existing node names if an asset is selected, otherwise an empty list."""
        if self.asset:
            return NodeManifest.get_existing()
        return []

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

    base_images: rx.Field[list[str]] = rx.field(default_factory=BaseImageManifest.get_existing)

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
        default_node = ""
        if cluster := next(iter(ClusterManifest.get_existing()), None):
            default_node = ClusterManifest.load(name=cluster).spec.defaults.node
        return self.form_data.get("node", default_node)

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
        certs = self.form_data.get("certificate_authorities") or "[]"
        return json.loads(certs)

    @rx.var
    def step_names_in_order(self) -> list[str]:
        """Get the names of workflow steps in their configured order."""
        return [self.steps_config[step["id"]].name for step in self.step_order]

    @rx.var
    def available_image_stores(self) -> list[str]:
        """Return a list of available image storage locations for the selected node."""
        if self.node:
            return NodeManifest.load(name=self.node).list_storages(content_type=StorageContentType.IMPORT)
        return []

    @rx.var
    def available_disk_stores(self) -> list[str]:
        """Return a list of available VM disk storage locations for the selected node."""
        if self.node:
            return NodeManifest.load(name=self.node).list_storages(content_type=StorageContentType.IMAGES)
        return []

    @rx.var
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


class CustomImagesTableState(CacheBuster, rx.State):
    """State management for the custom images table."""

    @rx.var(deps=["_cached_custom_images"])
    def custom_images(self) -> list[CustomImageManifest]:
        """Return a list of loaded CustomImageManifest instances for existing custom images."""
        return [CustomImageManifest.load(name=name) for name in CustomImageManifest.get_existing()]
