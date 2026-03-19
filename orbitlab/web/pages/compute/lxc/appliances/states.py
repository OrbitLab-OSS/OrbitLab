"""OrbitLab LXC States."""

import json
from typing import Literal

import reflex as rx

from orbitlab.data_types import ApplianceType, StorageContentType, WorkflowStepType
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.compute_templates.appliances import BaseApplianceManifest, CustomApplianceManifest
from orbitlab.manifest.compute_templates.workflow_models import FileConfig, WorkflowStep
from orbitlab.manifest.nodes import NodeManifest
from orbitlab.proxmox.compute_templates import ApplianceInfo, ProxmoxComputeTemplates
from orbitlab.web import components
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.utilities import CacheBuster, get_redis

from .models import ApplianceItemDownload


class BaseApplianceTableState(CacheBuster, rx.State):
    """State management for base LXC appliances."""

    @rx.var(deps=["_cached_base_appliances"])
    def base_appliances(self) -> list[BaseApplianceManifest]:
        """Get all existing base appliance manifests."""
        return [BaseApplianceManifest.load(name=name) for name in BaseApplianceManifest.get_existing()]


async def get_workflow_status(manifest_name: str) -> str:
    """Retrieve a value from Redis for a given manifest and key."""
    redis = get_redis()
    status = await redis.hget(name=f"ol:appliance:{manifest_name}", key="status")
    if isinstance(status, bytes):
        return status.decode()
    return "Never Ran"


class CustomApplianceTableState(CacheBuster, rx.State):
    """State management for custom LXC appliances."""
    workflow_to_view: str = ""

    @rx.var(deps=["_cached_custom_appliances"])
    def custom_appliances(self) -> list[CustomApplianceManifest]:
        """Get all existing custom appliance manifests."""
        return [CustomApplianceManifest.load(name=name) for name in CustomApplianceManifest.get_existing()]

    @rx.var(deps=["_cached_logs"])
    async def logs(self) -> str:
        """Workflow logs."""
        if self.workflow_to_view:
            redis = get_redis()
            if logs := await redis.hget(name=f"ol:appliance:{self.workflow_to_view}", key="logs"):
                logs: bytes
                return logs.decode()
        return ""

    @rx.var
    async def workflow_states(self) -> dict[str, str]:
        """Mapping of manifest names to Workflow States."""
        return {
            manifest.name: await get_workflow_status(manifest_name=manifest.name)
            for manifest in self.custom_appliances
        }


class DownloadApplianceState(rx.State):
    """State management for downloading appliances from Proxmox."""

    appliance_view: rx.Field[ApplianceType] = rx.field(default=ApplianceType.SYSTEM)
    query_string: rx.Field[str] = rx.field(default="")
    download_configs: rx.Field[dict[str, ApplianceItemDownload]] = rx.field(default_factory=dict)
    nodes: rx.Field[list[str]] = rx.field(default_factory=NodeManifest.get_existing)
    selected_node: rx.Field[str] = rx.field(default="")

    _turnkey_appliances: rx.Field[list[ApplianceInfo]] = rx.field(default_factory=list)
    _system_appliances: rx.Field[list[ApplianceInfo]] = rx.field(default_factory=list)

    @rx.var
    def turnkey_appliances(self) -> list[ApplianceInfo]:
        """Get the list of turnkey appliances filtered by the query string."""
        if self.query_string:
            return [apl for apl in self._turnkey_appliances if self.query_string in apl.template.lower()]
        return self._turnkey_appliances

    @rx.var
    def system_appliances(self) -> list[ApplianceInfo]:
        """Get the list of system appliances filtered by the query string."""
        if self.query_string:
            return [apl for apl in self._system_appliances if self.query_string in apl.template.lower()]
        return self._system_appliances

    @rx.event
    async def load(self) -> None:
        """Load available appliances from Proxmox, filtering out existing ones and updating state."""
        self.reset()
        default_node: str = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing()))).spec.defaults.node
        default_storages = NodeManifest.load(name=default_node).list_storages(content_type=StorageContentType.VZTMPL)
        existing = [
            BaseApplianceManifest.load(name=name).spec.template for name in BaseApplianceManifest.get_existing()
        ]
        for appliance in ProxmoxComputeTemplates().list_appliances():
            if appliance.template in existing:
                continue
            if appliance.is_turnkey:
                self.turnkey_appliances.append(appliance)
            else:
                self.system_appliances.append(appliance)
            self.download_configs[appliance.template] = ApplianceItemDownload(
                node=default_node,
                available_storage=default_storages,
            )


class CustomApplianceState(rx.State):
    """State management for custom appliance creation dialog."""

    edit_mode: rx.Field[bool] = rx.field(default=False)
    appliance_id: rx.Field[str] = rx.field(default="")

    nodes: rx.Field[list[str]] = rx.field(default_factory=NodeManifest.get_existing)

    memory_gb: int = 2
    swap_gb: int = 1

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
            return f"Edit Appliance: {self.appliance_id}"
        return "Create Custom Appliance"

    @rx.var
    def node(self) -> str:
        """Get the selected node name from form data."""
        return self.form_data.get("node", "")

    @rx.var
    def storage(self) -> str:
        """Get the selected storage name from form data."""
        return self.form_data.get("storage", "")

    @rx.var
    async def rootfs(self) -> str:
        """Get the selected rootfs name from form data."""
        return self.form_data.get("rootfs", "")

    @rx.var
    def sector(self) -> str:
        """Get the selected sector name from form data."""
        return self.form_data.get("sector", "")

    @rx.var
    def step_types(self) -> list[str]:
        """Get the available workflow step types for custom appliance creation."""
        return list(WorkflowStepType)

    @rx.var
    def name(self) -> str:
        """Get the appliance name from form data."""
        return self.form_data.get("name", "")

    @rx.var
    def base_appliance(self) -> str:
        """Get the selected base appliance name from form data."""
        return self.form_data.get("base_appliance", "")

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

    @rx.var(cache=False)
    def available_appliances(self) -> dict[str, str]:
        """Get a mapping of appliance display names to appliance names."""
        return {
            f"{BaseApplianceManifest.load(name=name).spec.template} ({name})": name
            for name in BaseApplianceManifest.get_existing()
        }

    @rx.var
    def available_storage(self) -> list[str]:
        """Get the available storage options for the selected node."""
        if self.node:
            return ProxmoxComputeTemplates().list_storages_for_node(
                node=self.node, content_type=StorageContentType.VZTMPL,
            )
        return []

    @rx.var
    def available_rootfs(self) -> list[str]:
        """Get the available rootfs options for the selected node."""
        if self.node:
            return ProxmoxComputeTemplates().list_storages_for_node(
                node=self.node, content_type=StorageContentType.ROOTDIR,
            )
        return []

    @rx.event
    async def load_appliance(self, appliance: CustomApplianceManifest) -> None:
        """Populate the state with data from an existing custom appliance manifest for editing."""
        self.appliance_id = appliance.name
        self.memory_gb = appliance.spec.memory
        self.swap_gb = appliance.spec.swap
        self.form_data = {
            "name": appliance.metadata.name,
            "base_appliance": appliance.spec.base_appliance,
            "node": appliance.spec.node,
            "storage": appliance.spec.storage,
            "rootfs": appliance.spec.rootfs,
            "sector": appliance.spec.sector,
        }
        for index, step in enumerate(appliance.spec.steps):
            self.step_order.append({"id": index})
            self.steps_config[index] = WorkflowStep.model_validate(step.model_dump())


class DeleteApplianceState(rx.State):
    """State management for deleting a custom appliance, including confirmation logic."""

    name: str = "UNKNOWN"
    appliance_type: Literal["base", "custom"] = "base"
    confirmation: str = ""

    @rx.var
    def delete_disabled(self) -> bool:
        """Return True if the delete action should be disabled (name and confirmation do not match)."""
        return self.name != self.confirmation
