import asyncio
from collections.abc import Callable
from ipaddress import IPv4Network
import os
from typing import Any, Final, Literal, get_args

import reflex as rx
from reflex.utils.prerequisites import get_app

from orbitlab.constants import NetworkSettings
from orbitlab.manifest.nodes import NodeManifest
from orbitlab.proxmox import ProxmoxCluster, ProxmoxComputeTemplates, ProxmoxNetworks, ProxmoxCompute
from orbitlab.proxmox.base.models import Task
from orbitlab.proxmox.compute_templates.models import OrbitLabAppliance
from orbitlab.web import components
from orbitlab.data_types import FrontendEvents, InitializationStatus, OrbitLabApplianceType, StorageContentType
from orbitlab.manifest.cluster import ClusterManifest, InfraAppliance, StorageProfile
from orbitlab.services.discovery import DiscoveryService
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.utilities import EventGroup


class Initializer:
    
    def __init__(self) -> None:
        self.discovery = DiscoveryService()
        
    @classmethod
    def check_initialized(cls) -> InitializationStatus:
        existing = ClusterManifest.get_existing()
        if existing and ClusterManifest.load(name=next(iter(existing))).metadata.initialized:
            return InitializationStatus.COMPLETE
        return InitializationStatus.NOT_STARTED
        
    async def run_sync(self, func: Callable, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return await asyncio.get_event_loop().run_in_executor(executor=None, func=lambda: func(*args, **kwargs))
        
    async def _emit(self, event: rx.event.EventCallback[*tuple[()]]) -> None:
        events = [event]

        app: rx.App = get_app().app
        async for token in app.event_namespace._token_manager.enumerate_tokens():  # noqa: SLF001
            await app.event_namespace.emit_update(
                update=rx.state.StateUpdate(
                    events=rx.event.fix_events(
                        events=[e for e in events if isinstance(e, rx.event.EventHandler | rx.event.EventSpec)],
                        token=token,
                        router_data={"token": token},
                    ),
                    final=None,
                ),
                token=token,
            )
        
    async def _configure_frr(self, node: str) -> None:
        await self.update_progress(f"Configuring {node} (this may take a few minutes)...")
        remote_node = ProxmoxCluster().create_connection(node=node)
        await self.run_sync(remote_node.run_command, "apt update -y")
        await self.run_sync(remote_node.run_command, "apt install -y frr frr-pythontools")
        await self.run_sync(remote_node.run_command, "sed -i 's|bgpd=no|bgpd=yes|' /etc/frr/daemons")
        await self.run_sync(remote_node.run_command, "systemctl enable frr && systemctl restart frr")     

    async def update_progress(self, progress_info: str) -> None:
        await self._emit(event=InitializationState.update_progress(progress_info))
    
    async def error(self, error: str) -> None:
        await self._emit(event=InitializationState.set_error(error))
        
    async def create_cluster(self) -> None:
        if next(iter(ClusterManifest.get_existing()), None):
            return
        
        await self.update_progress("Running cluster discovery...")
        manifest = await self.run_sync(self.discovery.discover_cluster)
 
        if not manifest:
            return await self.error(
                (
                    "The Proxmox cluster is configured with only 2 active quorum nodes. This is not a supported state "
                    "by OrbitLab. Either install OrbitLab on each node individually or add another node to the cluster "
                    "and retry."
                )
            )
            
        await self.update_progress("Running node discovery...")
        await self.run_sync(self.discovery.discover_nodes, manifest=manifest)

    async def configure_nodes(self) -> None:
        manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        for node in manifest.spec.nodes.values():
            if not node.configured:
                await self._configure_frr(node=node.name)
                node.configured = True
                manifest.spec.nodes[node.name] = node
        manifest.save()

    async def backplane(self, operation: Literal["create", "discover"]) -> None:
        manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        if operation == "discover":
            backplane_info = ProxmoxNetworks().describe_backplane()
            manifest.spec.backplane.controller.asn = backplane_info.controller.asn
            manifest.spec.backplane.controller.peers = backplane_info.controller.peers
            manifest.spec.backplane.cidr_block = backplane_info.subnet.cidr
        else:
            await self.run_sync(ProxmoxNetworks().create_backplane, cluster=manifest)
        manifest.save()

    async def _download_appliance(self, appliance_type: OrbitLabApplianceType, appliance: OrbitLabAppliance) -> tuple[OrbitLabApplianceType, InfraAppliance]:
        manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        client = ProxmoxComputeTemplates()
        if appliance.filename.endswith(".qcow2"):
            storage = manifest.spec.defaults.storage.imports
            content = "import"
        else:
            storage = manifest.spec.defaults.storage.vztmpl
            content = "vztmpl"

        checksum_algorithm, checksum = appliance.digest.split(":")
        params = {
            "content": content,
            "url": appliance.browser_download_url,
            "filename": appliance.filename,
            "checksum": checksum,
            "checksum-algorithm": checksum_algorithm,
        }
        task = client.create(
            path=f"/nodes/{manifest.spec.defaults.node}/storage/{storage}/download-url", model=Task, **params,
        )
        await self.run_sync(client.wait_for_task, task=task)
        if appliance.filename.endswith(".qcow2"):
            stored = client.list_stored_images(node=manifest.spec.defaults.node, storage=storage)
            volume_id = stored.get_image(filename=appliance.filename).volid
        else:
            stored = client.list_stored_appliances(node=manifest.spec.defaults.node, storage=storage)
            volume_id = stored.get_appliance(filename=appliance.filename).volid
        
        return (
            appliance_type,
            InfraAppliance(node=manifest.spec.defaults.node, volume_id=volume_id),
        )

    async def download_infrastructure(self) -> None:
        manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        appliances = ProxmoxComputeTemplates().get_infrastructure_appliances()
        downloaded = await asyncio.gather(*[
            self._download_appliance(
                appliance_type=appliance_type,
                appliance=appliances.get_appliance(appliance_type=appliance_type),
            ) for appliance_type in get_args(OrbitLabApplianceType.__value__)
        ])
        manifest.metadata.infrastructure_appliances = {
            appliance_type: appliance for appliance_type, appliance in downloaded
        }
        manifest.metadata.infrastructure_version = appliances.version
        manifest.save()

    async def create_baseline_infrastructure(self) -> None:
        manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        client = ProxmoxCompute()
        node = client.__node__
        
        await self.update_progress("Creating Backplane DNS...")
        vmid = client.get_next_vmid()
        params = manifest.generate_backplane_dns_params(vmid=vmid)
        task = client.create(path=f"/nodes/{node}/lxc", model=Task, **params)
        await self.run_sync(client.wait_for_task, task=task)
        
        await self.update_progress("Starting Backplane DNS...")
        task = client.create(path=f"/nodes/{node}/lxc/{vmid}/status/start", model=Task)
        await self.run_sync(client.wait_for_task, task=task)
        
        await self.update_progress("Creating Orbital Relay...")
        vmid = client.get_next_vmid()
        params = manifest.generate_orbital_relay_params(vmid=vmid)
        task = client.create(path=f"/nodes/{node}/lxc", model=Task, **params)
        await self.run_sync(client.wait_for_task, task=task)
        
        await self.update_progress("Starting Orbital Relay...")
        task = client.create(path=f"/nodes/{node}/lxc/{vmid}/status/start", model=Task)
        await self.run_sync(client.wait_for_task, task=task)
        manifest.metadata.initialized = True
        manifest.save()
        
        await self.update_progress("Finalizing...")


class InitializationState(rx.State):
    status: rx.Field[InitializationStatus] = rx.field(default_factory=Initializer.check_initialized)
    process_info: rx.Field[str] = rx.field(default="")
    error: rx.Field[str] = rx.field(default="")
    
    nodes: rx.Field[list[str]] = rx.field(default_factory=list)
    default_node: rx.Field[str] = rx.field(default="")

    @rx.var
    def vztmpls(self) -> list[str]:
        """Return a list of storage names containing LXC templates for the selected node."""
        if self.default_node:
            return NodeManifest.load(name=self.default_node).list_storages(content_type=StorageContentType.VZTMPL)
        return []

    @rx.var
    def rootdirs(self) -> list[str]:
        """Return a list of storage names containing root directories for the selected node."""
        if self.default_node:
            return NodeManifest.load(name=self.default_node).list_storages(content_type=StorageContentType.ROOTDIR)
        return []

    @rx.var
    def backups(self) -> list[str]:
        """Return a list of storage names containing backups for the selected node."""
        if self.default_node:
            return NodeManifest.load(name=self.default_node).list_storages(content_type=StorageContentType.BACKUP)
        return []

    @rx.var
    def images(self) -> list[str]:
        """Return a list of storage names containing images for the selected node."""
        if self.default_node:
            return NodeManifest.load(name=self.default_node).list_storages(content_type=StorageContentType.IMAGES)
        return []

    @rx.var
    def snippets(self) -> list[str]:
        """Return a list of storage names containing snippets for the selected node."""
        if self.default_node:
            return NodeManifest.load(name=self.default_node).list_storages(content_type=StorageContentType.SNIPPETS)
        return []

    @rx.var
    def isos(self) -> list[str]:
        """Return a list of storage names containing ISO images for the selected node."""
        if self.default_node:
            return NodeManifest.load(name=self.default_node).list_storages(content_type=StorageContentType.ISO)
        return []

    @rx.var
    def imports(self) -> list[str]:
        """Return a list of storage names containing importable content for the selected node."""
        if self.default_node:
            return NodeManifest.load(name=self.default_node).list_storages(content_type=StorageContentType.IMPORT)
        return []

    @rx.var
    def storage_profiles(self) -> dict[str, str]:
        """Return available storage profiles for OrbitLab configuration."""
        if len(self.nodes) == 0:
            return {}
        if len(self.nodes) == 1:
            return {"Local (ZFS/LVM)": "local"}
        return {
            "Local (ZFS/LVM)": "local",
            # TODO: Cluster mode storage profile for shared storage
        }

    @rx.var
    def default_storage_profile(self) -> str:
        """Return the default storage profile based on available options."""
        if len(self.nodes) == 1:
            return "local"
        return ""

    @rx.event
    async def update_progress(self, value: str) -> None:
        self.process_info = value
        if self.status != InitializationStatus.RUNNING:
            self.status = InitializationStatus.RUNNING

    @rx.event
    async def set_error(self, value: str) -> None:
        self.error = value
        self.status = InitializationStatus.ABORTED
        return components.Dialog.open(ErrorDialog.dialog_id)

    @rx.event
    async def complete(self) -> None:
        self.process_info = "Initialization Complete."
        self.status = InitializationStatus.COMPLETE

    @rx.event(background=True)
    async def phase_1(self) -> None:
        initializer = Initializer()
        await initializer.create_cluster()
        await initializer.configure_nodes()
        
        if controller := ProxmoxNetworks().describe_evpn_controller():
            if not controller.is_orbitlab_controller:
                return await initializer.error(
                    (
                        f"An EVPN Controller '{controller.controller}' already exists. "
                        "Only one EVPN controller may exist in Proxmox. Delete the current controller and retry."
                    )
                )
            await initializer.backplane(operation="discover")
            return ConfigureDefaultsDialog.open
        return components.Dialog.open(ConfigureBackplaneDialog.dialog_id)

    @rx.event(background=True)
    async def phase_2(self) -> None:
        initializer = Initializer()
        await initializer.download_infrastructure()
        await initializer.create_baseline_infrastructure()
        return [
            InitializationState.complete,
            ClusterDefaults.cache_clear("_cluster"),
        ]


class ErrorDialog(EventGroup):
    """Dialog displayed when Proxmox cluster has an invalid configuration with only 2 nodes."""

    @staticmethod
    @rx.event
    async def retry(_: rx.State) -> FrontendEvents:
        """Retry the OrbitLab initialization process."""
        return [
            components.Dialog.close(ErrorDialog.dialog_id),
            InitializationState.phase_1,
        ]

    dialog_id: Final = "invalid-proxmox-configuration-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            "Invalid Proxmox Cluster State",
            rx.el.div(rx.el.p(InitializationState.error)),
            rx.el.div(
                components.Buttons.Primary("Retry", on_click=cls.retry),
                class_name="w-full flex justify-center items-center mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="w-fit h-fit",
        )


class ConfigureBackplaneDialog(EventGroup):
    """Dialog for configuring the backplane network settings during OrbitLab initialization."""

    @staticmethod
    @rx.event(background=True)
    async def create_backplane(state: InitializationState) -> FrontendEvents:
        await Initializer().backplane(operation="create")
        return ConfigureDefaultsDialog.open

    @staticmethod
    @rx.event
    async def on_submit(state: InitializationState, form: dict) -> FrontendEvents:
        """Handle form submission for configuring the backplane network."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        cluster_manifest.spec.backplane.cidr_block = IPv4Network(form["cidr_block"])
        cluster_manifest.spec.backplane.controller.asn = int(form["asn"])
        cluster_manifest.save()
        state.process_info = "Creating Backplane..."
        return [
            components.Dialog.close(ConfigureBackplaneDialog.dialog_id),
            ConfigureBackplaneDialog.create_backplane,
        ]

    dialog_id: Final = "configure-backplane-network-dialog"
    form_id: Final = "configure-backplane-network-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            "Configure Backplane Network",
            components.Callout(
                """OrbitLab requires a unique IPv4 CIDR block and ASN to assign to its Backplane network. Once this is
                configured, it CANNOT be reconfigured. Common default values has been pre-filled for your convenience.
                """,
                type="warning",
            ),
            rx.el.form(
                components.FieldSet(
                    "Backplane",
                    components.FieldSet.Field(
                        "CIDR Block: ",
                        components.Input(
                            default_value=NetworkSettings.BACKPLANE.DEFAULT_CIDR,
                            pattern=NetworkSettings.BACKPLANE.NETWORK_REGEX_PATTERN,
                            form=cls.form_id,
                            name="cidr_block",
                            required=True,
                            error="Must be a valid IPv4 CIDR Block between a /24 and a /8",
                        ),
                    ),
                    components.FieldSet.Field(
                        "ASN: ",
                        components.Input(
                            default_value=f"{NetworkSettings.BACKPLANE.ASN}",
                            pattern=r"^(?:6500[1-9]|650[1-9]\d|65[1-4]\d{2}|655[0-2]\d|6553[0-4])$",
                            form=cls.form_id,
                            name="asn",
                            required=True,
                            error="Must be a valid ASN between 65001 and 65534",
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.on_submit,
            ),
            rx.el.div(
                components.Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex justify-end mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="w-fit h-fit",
        )


class ConfigureDefaultsDialog(EventGroup):
    """Dialog for storage profile and defaults."""

    @staticmethod
    @rx.event
    async def open(state: InitializationState) -> FrontendEvents:
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        state.nodes = list(cluster_manifest.spec.nodes.keys())
        if len(state.nodes) == 1:
            state.default_node = state.nodes[0]
        return components.Dialog.open(ConfigureDefaultsDialog.dialog_id)

    @staticmethod
    @rx.event
    async def configure_defaults(state: InitializationState, form: dict) -> FrontendEvents:
        """Finalize OrbitLab settings by saving the cluster manifest with user-provided configuration."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        cluster_manifest.spec.defaults.storage_profile = StorageProfile(value=form["storage_profile"])
        cluster_manifest.spec.defaults.node = form["primary_node"]
        cluster_manifest.spec.defaults.storage.imports = form["imports"]
        cluster_manifest.spec.defaults.storage.vztmpl = form["vztmpl"]
        cluster_manifest.spec.defaults.storage.backup = form.get("backup", "")
        cluster_manifest.spec.defaults.storage.images = form.get("images", "")
        cluster_manifest.spec.defaults.storage.rootdir = form.get("rootdir", "")
        cluster_manifest.spec.defaults.storage.snippets = form.get("snippets", "")
        cluster_manifest.spec.defaults.storage.iso = form.get("iso", "")
        cluster_manifest.save()
        state.process_info = "Downloading Infrastructure Appliances..."
        return [
            components.Dialog.close(ConfigureDefaultsDialog.dialog_id),
            InitializationState.phase_2,
        ]

    @staticmethod
    @rx.event
    async def set_default_node(state: InitializationState, node: str) -> None:
        """Set the selected node in the state."""
        state.default_node = node

    dialog_id: Final = "configure-defaults-dialog"
    form_id: Final = "configure-defaults-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            "Configure OrbitLab Defaults",
            rx.el.form(
                components.FieldSet(
                    "Required",
                    components.FieldSet.Field(
                        "Storage Profile: ",
                        components.Select(
                            InitializationState.storage_profiles,
                            default_value=InitializationState.default_storage_profile,
                            placeholder="Select a storage profile",
                            form=cls.form_id,
                            name="storage_profile",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Proxmox Node: ",
                        components.Select(
                            InitializationState.nodes,
                            on_change=cls.set_default_node,
                            placeholder="Select Proxmox Node",
                            form=cls.form_id,
                            name="primary_node",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "LXC Template: ",
                        components.Select(
                            InitializationState.vztmpls,
                            placeholder="Select Storage",
                            form=cls.form_id,
                            name="vztmpl",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Imports: ",
                        components.Select(
                            InitializationState.imports,
                            placeholder="Select Storage",
                            form=cls.form_id,
                            name="imports",
                            required=True,
                        ),
                    ),
                ),
                components.FieldSet(
                    "Optional",
                    components.FieldSet.Field(
                        "LX Root FS: ",
                        components.Select(
                            InitializationState.rootdirs,
                            placeholder="Select Storage",
                            form=cls.form_id,
                            name="rootdir",
                            disabled=InitializationState.rootdirs.length() == 0,
                        ),
                    ),
                    components.FieldSet.Field(
                        "VM Disks: ",
                        components.Select(
                            InitializationState.images,
                            placeholder="Select Storage",
                            form=cls.form_id,
                            name="images",
                            disabled=InitializationState.images.length() == 0,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Snippets: ",
                        components.Select(
                            InitializationState.snippets,
                            placeholder="Select Storage",
                            form=cls.form_id,
                            name="snippets",
                            disabled=InitializationState.snippets.length() == 0,
                        ),
                    ),
                    components.FieldSet.Field(
                        "ISOs: ",
                        components.Select(
                            InitializationState.isos,
                            placeholder="Select Storage",
                            form=cls.form_id,
                            name="iso",
                            disabled=InitializationState.isos.length() == 0,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Back Ups: ",
                        components.Select(
                            InitializationState.backups,
                            placeholder="Select Storage",
                            form=cls.form_id,
                            name="backup",
                            disabled=InitializationState.backups.length() == 0,
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.configure_defaults,
            ),
            rx.el.div(
                components.Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex justify-end mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-[50vw] max-h-[80vh] h-fit",
        )
