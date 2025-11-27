"""OrbitLab LXC States."""

import json

import reflex as rx

from orbitlab.clients.proxmox.client import Proxmox
from orbitlab.clients.proxmox.models import ApplianceInfo
from orbitlab.data_types import ApplianceType, CustomApplianceStepType, ManifestKind, StorageContentType
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.appliances import BaseApplianceManifest, FilePush, Step
from orbitlab.web import components
from orbitlab.web.states.certificates import CertificateManifestsState

from .models import ApplianceItemDownload


class DownloadApplianceState(rx.State):
    """State management for downloading appliances from Proxmox.

    This class handles the retrieval and filtering of available appliances
    that can be downloaded from Proxmox nodes, including both system and
    turnkey appliances.
    """

    appliance_view: ApplianceType = ApplianceType.SYSTEM
    query_string: str = ""
    download_configs: dict[str, ApplianceItemDownload] = rx.field(default_factory=dict)
    existing: list[str] = rx.field(
        default_factory=lambda: ManifestClient().get_existing_by_kind(kind=ManifestKind.BASE_APPLIANCE),
    )

    @rx.var
    def available_appliances(self) -> list[ApplianceInfo]:
        """Get the list of available appliances from Proxmox that are not already downloaded."""
        appliances = []
        try:
            node = next(iter(ManifestClient().get_existing_by_kind(kind=ManifestKind.NODE).keys()))
        except StopIteration:
            return appliances
        else:
            download_configs = {}
            for appliance in Proxmox().list_appliances(node=node).root:
                if appliance.template in self.existing:
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
        return list(ManifestClient().get_existing_by_kind(kind=ManifestKind.NODE))


class CreateApplianceState(CertificateManifestsState):
    """State management for custom appliance creation dialog.

    This state class manages the form data, workflow steps configuration,
    and upload progress for creating custom appliances from base appliances.
    """
    form_data: rx.Field[dict] = rx.field(default_factory=dict)
    step_order: rx.Field[list[components.SortableItem]] = rx.field(default_factory=list)
    steps_config: rx.Field[dict[int, Step]] = rx.field(default_factory=dict)
    uploading: rx.Field[bool] = False
    upload_progress: rx.Field[int] = 0
    script_step: rx.Field[int | None] = None
    script_data: rx.Field[str] = ""
    files_step: rx.Field[int | None] = None
    files_data: rx.Field[list[FilePush] | None] = None

    @rx.var(cache=False)
    def base_appliances(self) -> list[str]:
        """Get the list of available base appliance names from the manifest client."""
        return list(ManifestClient().get_existing_by_kind(kind=ManifestKind.BASE_APPLIANCE).keys())

    @rx.var(cache=False)
    def nodes(self) -> list[str]:
        """Get the list of available node names from the manifest client."""
        return list(ManifestClient().get_existing_by_kind(kind=ManifestKind.NODE))

    @rx.var
    def available_storage(self) -> list[str]:
        """Get the available storage options for the selected node."""
        if self.node:
            node_manifest = ManifestClient().load(self.node, kind=ManifestKind.NODE)
            return [
                store.name for store in node_manifest.spec.storage.root if StorageContentType.VZTMPL in store.content
            ]
        return []

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
    def default_script_value(self) -> str:
        """Get the default script value for the currently selected script step."""
        if self.script_step is not None:
            return self.steps_config[self.script_step].script or ""
        return ""

    @rx.var
    def step_names_in_order(self) -> list[str]:
        """Get the names of workflow steps in their configured order."""
        return [self.steps_config[step["id"]].name for step in self.step_order]


def get_base_appliances() -> list[BaseApplianceManifest]:
    """Get all available base appliance manifests."""
    client = ManifestClient()
    return [
        client.load(name, kind=ManifestKind.BASE_APPLIANCE)
        for name in client.get_existing_by_kind(kind=ManifestKind.BASE_APPLIANCE)
    ]


class AppliancesState(rx.State):
    """State management for appliance-related data."""

    base_appliances: list[BaseApplianceManifest] = rx.field(default_factory=get_base_appliances)
