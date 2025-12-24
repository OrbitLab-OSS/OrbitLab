"""OrbitLab LXC States."""

import json

import reflex as rx

from orbitlab.clients.proxmox.appliances import ApplianceInfo, ProxmoxAppliances
from orbitlab.data_types import ApplianceType, CustomApplianceStepType
from orbitlab.manifest.appliances import FilePush, Step
from orbitlab.manifest.nodes import NodeManifest
from orbitlab.web import components
from orbitlab.web.states.manifests import ManifestsState

from .models import ApplianceItemDownload, Network


class DownloadApplianceState(ManifestsState):
    """State management for downloading appliances from Proxmox."""

    appliance_view: rx.Field[ApplianceType] = rx.field(default=ApplianceType.SYSTEM)
    query_string: rx.Field[str] = rx.field(default="")
    download_configs: rx.Field[dict[str, ApplianceItemDownload]] = rx.field(default_factory=dict)

    @rx.var
    def available_appliances(self) -> list[ApplianceInfo]:
        """Get the list of available appliances from Proxmox that are not already downloaded."""
        appliances = []
        node = next(iter(self.node_names), None)
        if not node:
            return appliances

        download_configs = {}
        for appliance in ProxmoxAppliances().list_appliances():
            if appliance.template in self.base_appliance_names:
                continue
            appliances.append(appliance)
            download_configs[appliance.template] = ApplianceItemDownload()
        self.download_configs = download_configs
        return sorted(appliances, key=lambda apl: apl.template)

    @rx.var
    def available_system_appliances(self) -> list[ApplianceInfo]:
        """Get the list of available system appliances filtered by query string."""
        system_appliances = []
        for apl in self.available_appliances:
            if apl.is_turnkey:
                continue
            if self.query_string and self.query_string not in apl.template.lower():
                continue
            system_appliances.append(apl)
        return system_appliances

    @rx.var
    def available_turnkey_appliances(self) -> list[ApplianceInfo]:
        """Get the list of available turnkey appliances filtered by query string."""
        turnkey_appliances = []
        for apl in self.available_appliances:
            if not apl.is_turnkey:
                continue
            if self.query_string and self.query_string not in apl.template.lower():
                continue
            turnkey_appliances.append(apl)
        return turnkey_appliances

    @rx.var
    def available_nodes(self) -> list[str]:
        """Get the list of available node names from the manifest client."""
        return NodeManifest.get_existing()


class CreateApplianceState(ManifestsState):
    """State management for custom appliance creation dialog.

    This state class manages the form data, workflow steps configuration,
    and upload progress for creating custom appliances from base appliances.
    """
    memory_gb: int = 2
    swap_gb: int = 1
    form_data: rx.Field[dict] = rx.field(default_factory=dict)
    step_order: rx.Field[list[components.SortableItem]] = rx.field(default_factory=list)
    steps_config: rx.Field[dict[int, Step]] = rx.field(default_factory=dict)
    network_order: rx.Field[list[components.SortableItem]] = rx.field(default_factory=list)
    networks: rx.Field[dict[int, Network]] = rx.field(default_factory=dict)
    uploading: rx.Field[bool] = rx.field(default=False)
    upload_progress: rx.Field[int] = rx.field(default=0)
    script_value: rx.Field[str] = rx.field(default="")
    default_script_value: rx.Field[str] = rx.field(default="")
    files_data: rx.Field[list[FilePush] | None]  = rx.field(default=None)

    @rx.var(cache=False)
    def nodes(self) -> list[str]:
        """Get the list of available node names from the manifest client."""
        return NodeManifest.get_existing()

    @rx.var
    def node_manifest(self) -> NodeManifest | None:
        if self.node:
            return NodeManifest.load(self.node)
        return None

    @rx.var
    def available_storage(self) -> list[str]:
        """Get the available storage options for the selected node."""
        # TODO: Fix
        return []

    @rx.var
    def available_networks(self) -> list[str]:
        return []
        # TODO: Fix (use Sectors instead)

    @rx.var
    def available_subnets(self) -> dict[str, dict[str, str]]:
        return {}
        # TODO: Fix (use Sectors instead)

    @rx.var
    def step_types(self) -> list[str]:
        """Get the available workflow step types for custom appliance creation."""
        return list(CustomApplianceStepType)

    @rx.var
    def name(self) -> str:
        """Get the appliance name from form data."""
        return self.form_data.get("name", "")

    @rx.var
    def base_appliance(self) -> str:
        """Get the selected base appliance name from form data."""
        return self.form_data.get("base_appliance", "")

    @rx.var
    def node(self) -> str:
        """Get the selected node name from form data."""
        return self.form_data.get("node", "")

    @rx.var
    def storage(self) -> str:
        """Get the selected storage name from form data."""
        return self.form_data.get("storage", "")

    @rx.var
    def root_certs(self) -> list[str]:
        """Get the selected root CAs from form data."""
        certs = self.form_data.get("certificate_authorities") or "[]"
        return json.loads(certs)

    @rx.var
    def step_names_in_order(self) -> list[str]:
        """Get the names of workflow steps in their configured order."""
        return [self.steps_config[step["id"]].name for step in self.step_order]
