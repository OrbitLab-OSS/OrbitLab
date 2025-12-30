"""OrbitLab LXC States."""

import json

import reflex as rx

from orbitlab.clients.proxmox.appliances import ApplianceInfo, ProxmoxAppliances
from orbitlab.data_types import ApplianceType, CustomApplianceStepType, StorageContentType
from orbitlab.manifest.appliances import BaseApplianceManifest, CustomApplianceManifest
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.nodes import NodeManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.web import components

from .models import ApplianceItemDownload, FileConfig, NetworkConfig, WorkflowStep


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
        existing = BaseApplianceManifest.get_existing()
        for appliance in ProxmoxAppliances().list_appliances():
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
    nodes: rx.Field[list[str]] = rx.field(default_factory=NodeManifest.get_existing)
    base_appliances: rx.Field[list[str]] = rx.field(default_factory=BaseApplianceManifest.get_existing)

    memory_gb: int = 2
    swap_gb: int = 1

    form_data: rx.Field[dict] = rx.field(default_factory=dict)
    step_order: rx.Field[list[components.SortableItem]] = rx.field(default_factory=list)
    steps_config: rx.Field[dict[int, WorkflowStep]] = rx.field(default_factory=dict)
    network_order: rx.Field[list[components.SortableItem]] = rx.field(default_factory=list)
    networks: rx.Field[dict[int, NetworkConfig]] = rx.field(default_factory=dict)
    uploading: rx.Field[bool] = rx.field(default=False)
    upload_progress: rx.Field[int] = rx.field(default=0)
    script_value: rx.Field[str] = rx.field(default="")
    default_script_value: rx.Field[str] = rx.field(default="")
    files_data: rx.Field[list[FileConfig] | None]  = rx.field(default=None)

    @rx.var
    def node(self) -> str:
        """Get the selected node name from form data."""
        return self.form_data.get("node", "")

    @rx.var
    def available_storage(self) -> list[str]:
        """Get the available storage options for the selected node."""
        if self.node:
            return NodeManifest.load(name=self.node).list_storages(content_type=StorageContentType.VZTMPL)
        return []

    @rx.var
    def available_rootfs(self) -> list[str]:
        """Get the available rootfs options for the selected node."""
        if self.node:
            return NodeManifest.load(name=self.node).list_storages(content_type=StorageContentType.ROOTDIR)
        return []

    @rx.var
    def storage(self) -> str:
        """Get the selected storage name from form data."""
        if "storage" in self.form_data:
            return self.form_data["storage"]
        cluster = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        return cluster.get_storage(content_type=StorageContentType.VZTMPL)

    @rx.var
    def rootfs(self) -> str:
        """Get the selected rootfs name from form data."""
        if "rootfs" in self.form_data:
            return self.form_data["rootfs"]
        cluster = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        return cluster.get_storage(content_type=StorageContentType.ROOTDIR)

    @rx.var
    def sectors(self) -> dict[str, str]:
        """Get a mapping of sector display names to sector names."""
        return {
            f"{sector.name} ({sector.spec.cidr_block})": sector.name
            for sector in [SectorManifest.load(name=name) for name in SectorManifest.get_existing()]
        }

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
    def root_certs(self) -> list[str]:
        """Get the selected root CAs from form data."""
        certs = self.form_data.get("certificate_authorities") or "[]"
        return json.loads(certs)

    @rx.var
    def step_names_in_order(self) -> list[str]:
        """Get the names of workflow steps in their configured order."""
        return [self.steps_config[step["id"]].name for step in self.step_order]

    @rx.event
    async def load_appliance(self, appliance: CustomApplianceManifest) -> None:
        """Populate the state with data from an existing custom appliance manifest for editing."""
        self.reset()
        self.memory_gb = appliance.spec.memory
        self.swap_gb = appliance.spec.swap
        self.form_data = {
            "name": appliance.name,
            "base_appliance": appliance.spec.base_appliance,
            "node": appliance.spec.node,
            "storage": appliance.spec.storage,
            "rootfs": appliance.spec.rootfs,
            "certificate_authorities": appliance.spec.certificate_authorities,
        }
        for index, step in enumerate(appliance.spec.steps):
            self.step_order.append({"id": index})
            self.steps_config[index] = WorkflowStep.model_validate(step.model_dump())
        for index, network in enumerate(appliance.spec.networks):
            sector = SectorManifest.load(name=network.sector.name)
            self.network_order.append({"id": index})
            self.networks[index] = NetworkConfig(
                sector=network.sector.name,
                subnet=network.subnet,
                available_subnets = {
                    (
                        f"{subnet.name} ({subnet.cidr_block}, "
                        f"Available: {sector.get_available_ips(subnet_name=subnet.name)})"
                    ): subnet.name
                    for subnet in sector.spec.subnets
                },
            )


class DeleteCustomApplianceState(rx.State):
    """State management for deleting a custom appliance, including confirmation logic."""

    name: str = "UNKNOWN"
    confirmation: str = ""

    @rx.var
    def delete_disabled(self) -> bool:
        """Return True if the delete action should be disabled (name and confirmation do not match)."""
        return self.name != self.confirmation


def _all_appliances() -> list[str]:
    return BaseApplianceManifest.get_existing() + CustomApplianceManifest.get_existing()


class LaunchLXCState(rx.State):
    """State management for launching LXC containers, including form data and available options."""

    form_data: rx.Field[dict] = rx.field(default_factory=dict)

    appliances: rx.Field[list[str]] = rx.field(default_factory=_all_appliances)

    memory_gb: rx.Field[int] = rx.field(default=2)
    swap_gb: rx.Field[int] = rx.field(default=1)
    disk_size_gb: rx.Field[int] = rx.field(default=8)
    cores: rx.Field[int] = rx.field(default=2)
    sector: rx.Field[str] = rx.field(default="")

    @rx.var
    def available_rootfs(self) -> list[str]:
        """Get the available rootfs options for the selected node."""
        if self.node:
            return NodeManifest.load(name=self.node).list_storages(content_type=StorageContentType.ROOTDIR)
        return []

    @rx.var
    def name(self) -> str:
        """LXC hostname."""
        return self.form_data.get("name", "")

    @rx.var
    def node(self) -> str:
        """LXC Proxmox node."""
        return self.form_data.get("node", "")

    @rx.var
    def appliance(self) -> str:
        """LXC appliance."""
        return self.form_data.get("appliance", "")

    @rx.var
    def subnet(self) -> str:
        """LXC Subnet."""
        return self.form_data.get("subnet", "")

    @rx.var
    def rootfs(self) -> str:
        """LXC Root FS store."""
        if "rootfs" in self.form_data:
            return self.form_data["rootfs"]
        cluster = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        return cluster.get_storage(content_type=StorageContentType.ROOTDIR)

    @rx.var
    def sectors(self) -> dict[str, str]:
        """Available Sectors."""
        """Get a mapping of sector display names to sector names."""
        return {
            f"{sector.name} ({sector.spec.cidr_block})": sector.name
            for sector in [SectorManifest.load(name=name) for name in SectorManifest.get_existing()]
        }

    @rx.var
    def subnets(self) -> dict[str, str]:
        """Available Subnets in selected Sector."""
        if self.sector:
            sector_manifest = SectorManifest.load(name=self.sector)
            return {
                (
                    f"{subnet.name} ({subnet.cidr_block}, "
                    f"Available: {sector_manifest.get_available_ips(subnet_name=subnet.name)})"
                ): subnet.name
                for subnet in sector_manifest.spec.subnets
            }
        return {}
