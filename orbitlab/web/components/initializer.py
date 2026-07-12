
import asyncio
from ipaddress import IPv4Network
from typing import Final
import httpx
from typing_extensions import get_args

import reflex as rx

from orbitlab.constants import USER_ACKNOWLEDGEMENT
from orbitlab.proxmox.client import Proxmox
from orbitlab.proxmox.exceptions import PctExecError
from orbitlab.redis.clients import BackplaneClient, ClusterClient, DNSClient, ETCDClient
from orbitlab.redis.models import ARecord, BackplaneConfig, Controller, InfraAppliance, InfraAppliances, NodeConfig, SRVRecord
from orbitlab.web import tailwind
from orbitlab.data_types import ETCDStatus, FrontendEvents, InitializationStatus, OrbitLabApplianceType
from orbitlab.web.components.dialogs.cluster_settings import ClusterSettingsDialogState
from orbitlab.web.global_state import ETCDState, OrbitLabState, SelectionDefaults
from orbitlab.web.tailwind.dialog import DialogStateManager
from orbitlab.web.components.sidebar import ClusterSettingsDialog
from orbitlab.web.utilities import EventGroup


class InitializationState(rx.State):
    progress_message: rx.Field[str] = rx.field(default="")
    error_title: rx.Field[str] = rx.field(default="")
    error_message: rx.Field[str] = rx.field(default="")
    can_retry: rx.Field[bool] = rx.field(default=False)


@rx.event(background=True)
async def wait_for_default_settings(state: InitializationState) -> FrontendEvents:
    opened = False
    while True:
        async with state:
            registered = await state.get_var_value(DialogStateManager.registered)
        if registered.get(ClusterSettingsDialog.dialog_id, False):
            opened = True
        if opened and not registered.get(ClusterSettingsDialog.dialog_id, False):
            break
        await asyncio.sleep(1)
    return download_infrastructure


@rx.event(background=True)
async def download_infrastructure(state: InitializationState) -> FrontendEvents:
    async with state:
        state.progress_message = "Downloading Infrastructure..."
        defaults = await state.get_var_value(SelectionDefaults.defaults)
        
    latest_infra = await Proxmox().get_infrastructure_appliances()
    
    appliances = InfraAppliances(appliances={}, version=latest_infra.version)
    for appliance_type in get_args(OrbitLabApplianceType.__value__):
        async with state:
            state.progress_message = f"Downloading Infrastructure ({appliance_type})..."
            
        appliance = latest_infra.get_appliance(appliance_type=appliance_type)
        if appliance.filename.endswith(".qcow2"):
            storage = defaults.imports
            content = "import"
        else:
            storage = defaults.vztmpl
            content = "vztmpl"
            
        checksum_algorithm, checksum = appliance.digest.split(":")
        params = {
            "content": content,
            "url": appliance.browser_download_url,
            "filename": appliance.filename,
            "checksum": checksum,
            "checksum-algorithm": checksum_algorithm,
        }
        volume_id = await Proxmox().download_infrastructure_appliance(
            storage=storage, params=params, node=defaults.node,
        )
        appliances.add(
            appliance_type=appliance_type, appliance=InfraAppliance(node=defaults.node, volume_id=volume_id),
        )
    await ClusterClient().set_infra_appliances(appliances=appliances)
    return create_backplane_controller


@rx.event(background=True)
async def create_backplane_controller(state: InitializationState) -> FrontendEvents:
    async with state:
        state.progress_message = "Creating Backplane Controller..."
    proxmox = Proxmox()
    vmid = await proxmox.get_next_vmid()
    params = await BackplaneClient().generate_backplane_params(vmid=vmid)
    await proxmox.create_instance(instance_type="lxc", params=params)
    
    async with state:
        state.progress_message = "Starting Backplane Controller..."
    await proxmox.start(vmid=vmid)
    await BackplaneClient().set_vmid(vmid=vmid)
    
    return create_etcd_cluster


@rx.event(background=True)
async def create_etcd_cluster(state: InitializationState) -> FrontendEvents:
    async with state:
        state.progress_message = "Creating ETCD Cluster..."
    
    client = ETCDClient()
    proxmox = Proxmox()
    dns = DNSClient()
    await proxmox.create_pool(pool_id="orbitlab-etcd", alias="OrbitLab's ETCD Cluster")
    
    for i in range(3):
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_create_params(vmid=vmid)
        await proxmox.create_instance(instance_type="lxc", params=params)
    
    appliances = await ClusterClient().get_infra_appliances()
    await client.set_version(version=appliances.version)
    
    async with state:
        state.progress_message = "Creating ETCD DNS Records..."
    
    members = await client.list_members()
    client_access_records: list[ARecord] = []
    peer_srv_records: list[SRVRecord] = []
    client_srv_records: list[SRVRecord] = []
    for member in members:
        # 'A' Record pointing ETCD member hostname to address 
        await dns.add_backplane_a_records(member.name, ARecord(ip=member.address.ip))
        # 'A' Record pointing `etcd.orbitlab.internal` to all members
        client_access_records.append(ARecord(ip=member.address.ip))
        # 'SRV' peer (server) record pointing to peer-facing FQDNs and port for ETCD Discovery
        peer_srv_records.append(SRVRecord(target=member.name, port=2380))
        # 'SRV' client record pointing to client-facing FQDNs and port for ETCD Discovery
        client_srv_records.append(SRVRecord(target=member.name, port=2379))
    await asyncio.gather(
        dns.add_backplane_a_records("etcd", *client_access_records),
        dns.add_backplane_srv_records("etcd-server", "tcp", *peer_srv_records),
        dns.add_backplane_srv_records("etcd-client", "tcp", *client_srv_records)
    )
    
    async with state:
        state.progress_message = "Starting ETCD Cluster..."
    
    await asyncio.gather(
        *(proxmox.start(vmid=member.vmid) for member in await client.list_members()),
    )
    
    async with state:
        state.progress_message = "ETCD Cluster warming up... (Grab a coffee. Might take a couple minutes)"
    
    await asyncio.sleep(120)
    
    async with state:
        state.progress_message = "Checking ETCD Cluster health..."
    
    async with await proxmox.create_connection() as connection:
        for member in await client.list_members():
            try:
                await connection.lxc_execute_script(vmid=member.vmid, content="/usr/bin/etcd-mgr health-check")
            except PctExecError as err:
                async with state:
                    state.progress_message = ""
                    state.error_title = "ETCD Cluster Creation Failure"
                    state.error_message = (
                        "While creating the ETCD cluster, OrbitLab encountered the following error for "
                        f"member {member.name}: '{err}'. "
                        "This may be a transient error. So, you can retry the initialization process. If the error "
                        "occurs again, it is recommended to open an issue on GitHub."
                    )
                    state.can_retry = True
                return set_initialization_failed
            else:
                async with state:
                    state.progress_message = f"ETCD member {member.name} is healthy"
    
    await ETCDClient().set_status(status=ETCDStatus.AVAILABLE)
    
    async with state:
        state.progress_message = "Complete."
    return [
        set_initialization_complete,
        ETCDState.cache_clear("status")
    ]


@rx.event
async def set_initialization_complete(state: OrbitLabState) -> FrontendEvents:
    state.status = InitializationStatus.COMPLETE
    await ClusterClient().set_initialized()
    return rx.redirect("/")


@rx.event
async def set_initialization_failed(state: OrbitLabState) -> FrontendEvents:
    state.status = InitializationStatus.FAILED
    return tailwind.Dialog.open(ErrorDialog.dialog_id)


class ConfigureBackplaneDialog(EventGroup):
    """Dialog for configuring the backplane network settings during OrbitLab initialization."""

    network_regex_pattern: Final = (
        r"^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\/(?:[89]|1\d|2[0-4])$"
    )
    default_cidr: Final = "100.96.0.0/16"

    @staticmethod
    @rx.event(background=True)
    async def create_backplane(state: InitializationState, backplane_network: str) -> FrontendEvents:
        client = BackplaneClient()
        proxmox = Proxmox()
        
        cidr_block = IPv4Network(backplane_network)
        mtu = await proxmox.get_mtu()
        nodes = await ClusterClient().list_nodes()
        
        zone_tag = await client.get_next_vlan_tag(start=10, end=99)
        if not zone_tag:
            async with state:
                state.progress_message = ""
                state.error_title = "Zone VLAN Tag Unavailable"
                state.error_message = (
                    "OrbitLab uses a VLAN tag between 10 and 99, whichever lowest number is available, to assign to "
                    "the Backplane EVPN Zone. During its discovery of VLAN tags already in use, all of the tags "
                    "between 10 and 99 were detected to be in-use. You can release one by removing an SDN object or "
                    "resource and Retry the initialization process."
                )
                state.can_retry = True
            return set_initialization_failed
        
        vnet_tag = await client.get_next_vlan_tag(start=100, end=999)
        if not vnet_tag:
            async with state:
                state.progress_message = ""
                state.error_title = "VNet VLAN Tag Unavailable"
                state.error_message = (
                    "OrbitLab uses a VLAN tag between 100 and 999, whichever lowest number is available, to assign to "
                    "the Backplane VXLAN VNet. During its discovery of VLAN tags already in use, all of the tags "
                    "between 100 and 999 were detected to be in-use. You can release one by removing an SDN object or "
                    "resource and Retry the initialization process."
                )
                state.can_retry = True
            return set_initialization_failed
        
        # TODO: When Cluster Operations support is implemented, we need to install the DEB file on all other nodes.
        # This will need to be the spot to do it, so this is the placeholder.
            
        async with state:
            state.progress_message = "Creating Backplane Network..."
            
        backplane = BackplaneConfig(
            cidr_block=cidr_block,
            controller=Controller(peers=[node.config.address for node in nodes]),
            zone_tag=zone_tag,
            vnet_tag=vnet_tag,
            mtu=mtu - 50,
            exit_nodes=[node.config.name for node in nodes]
        )
        await BackplaneClient().set(backplane=backplane)
        await proxmox.create_backplane(backplane=backplane)
        
        lan_network = await ClusterClient().get_lan_network()
        try:
            await proxmox.create_fabric(lan_network=lan_network)
            for node in nodes:
                await proxmox.add_node_to_fabric(node=node.config.name, address=node.config.address)
        except httpx.HTTPStatusError as err:
            async with state:
                state.progress_message = ""
                state.error_title = "OSPF Fabric Creation Error"
                state.error_message = (
                    "Received the following error when attempting to create the OSPF Fabric: "
                    f"{err.response.reason_phrase}. Please remediate the issue before retrying the "
                    "initialization process."
                )
                state.can_retry = True
            return set_initialization_failed
        
        return [
            wait_for_default_settings,
            ClusterSettingsDialogState.initalize,
        ]

    @staticmethod
    @rx.event
    async def on_submit(state: InitializationState, form: dict) -> FrontendEvents:
        """Handle form submission for configuring the backplane network."""
        backplane_cidr: str = form["cidr_block"]
        lan_network = await ClusterClient().get_lan_network()
        if IPv4Network(backplane_cidr, strict=False).overlaps(lan_network):
            return rx.toast.error(f"The Backplane network {backplane_cidr} overlaps with the vmbr0 network {lan_network}")
        
        state.progress_message = "Generating Backplane configuration..."
        return [
            tailwind.Dialog.close(ConfigureBackplaneDialog.dialog_id),
            ConfigureBackplaneDialog.create_backplane(backplane_cidr)
        ]

    dialog_id: Final = "orbitlab-initial-backplane-configuration-dialog"
    form_id: Final = "orbitlab-initial-backplane-configuration-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
            "Configure Backplane Network",
            tailwind.Callout(
                (
                    "OrbitLab requires a unique IPv4 CIDR block to assign to its Backplane network. Once this is set, "
                    "it CANNOT be reconfigured. A Common default value has been pre-filled for your convenience."
                ),
                type="warning",
            ),
            rx.el.form(
                tailwind.FieldSet(
                    "Backplane",
                    tailwind.FieldSet.Field(
                        "CIDR Block: ",
                        tailwind.Input(
                            default_value=cls.default_cidr,
                            pattern=cls.network_regex_pattern,
                            form=cls.form_id,
                            name="cidr_block",
                            required=True,
                            error="Must be a valid IPv4 CIDR Block between a /24 and a /8",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "ASN: ",
                        tailwind.Input(
                            default_value="65001",
                            disabled=True,
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.on_submit,
            ),
            rx.el.div(
                tailwind.Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex justify-end mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="w-fit h-fit",
        )


class InitialConfigurationDialog(EventGroup):
    
    @staticmethod
    @rx.event(background=True)
    async def initial_checks(state: InitializationState) -> FrontendEvents:
        client = Proxmox()
        
        async with state:
            state.progress_message = "Discovering SDN Controllers..."
        controllers = await client.list_controllers()
        if existing := controllers.get_evpn_controller():
            async with state:
                state.progress_message = ""
                state.error_title = "Existing EVPN Controller"
                state.error_message = (
                    f"An existing EVPN controller '{existing.controller}' was discovered. Since Proxmox only allows a "
                    "single EVPN controller per cluster, we do not want to override existing infrastructure that may be "
                    "using it. If not in use, please remove it via the Proxmox CLI or web UI and click Retry."
                )
                state.can_retry = True
            return set_initialization_failed
        
        async with state:
            state.progress_message = "Discovering Proxmox nodes..."
        nodes = await client.list_nodes()
        if len(nodes) > 1:
            async with state:
                state.progress_message = ""
                state.error_title = "Cluster Unsupported"
                state.error_message = (
                    "OrbitLab only supports single-node Proxmox installations. Cluster operations are not "
                    "currently supported, but are on the roadmap for support. The main roadblock is shared storage "
                    "configuration and management versus having to deal with local storage and replication to other nodes."
                )
                state.can_retry = False
            return set_initialization_failed
        
        cluster = ClusterClient()
        for node in nodes:
            await cluster.set_node(
                node=NodeConfig(
                    name=node.name,
                    address=node.ip,
                    proxmox_version=await client.get_node_proxmox_version(node=node.name),
                )
            )
            await cluster.set_node_online(node=node.name, online=node.online)
        
        async with state:
            state.progress_message = "Discovering external LAN network..."
        vmbr0_bridge = await client.get_vmbr0_for_node(node=nodes[0].name)
        await ClusterClient().set_lan_network(network=vmbr0_bridge.cidr.network)
        
        async with state:
            state.progress_message = "Discovering existing VNets..."
        vnets = await client.list_vnets()
        await BackplaneClient().add_used_vlan_tags(tags=vnets.get_all_tags())
        return [
            OrbitLabState.cache_clear("nodes"),
            tailwind.Dialog.open(ConfigureBackplaneDialog.dialog_id)
        ]
    
    dialog_id: Final = "orbitlab-initial-configuration-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
            "User Acknowledgement",
            tailwind.Callout(
                (
                    "OrbitLab is currently alpha software and under heavy active development. Things may change, "
                    "break, or require manual cleanup between versions. Use it only in lab or non-production "
                    "environments for now."
                ),
                type="warning",
                class_name="my-2",
            ),
            rx.el.div(
                rx.markdown(USER_ACKNOWLEDGEMENT),
                class_name="w-full",
            ),
            rx.el.div(
                tailwind.Buttons.Primary(
                    "Submit",
                    on_click=[
                        tailwind.Dialog.close(InitialConfigurationDialog.dialog_id),
                        cls.initial_checks,
                    ]
                ),
                class_name="w-full flex justify-center items-center mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-[75vw] h-fit",
        )


class ErrorDialog(EventGroup):

    @staticmethod
    @rx.event
    async def retry(state: InitializationState) -> FrontendEvents:
        """Retry the OrbitLab initialization process."""
        state.reset()
        return InitializationDialogs.initialize

    dialog_id: Final = "orbitlab-initial-configuration-error-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
            f"{InitializationState.error_title}",
            rx.el.div(rx.el.p(InitializationState.error_message)),
            rx.cond(
                InitializationState.can_retry,
                rx.el.div(
                    tailwind.Buttons.Primary("Retry", on_click=cls.retry),
                    class_name="w-full flex justify-center items-center mt-4",
                ),
            ),
            dialog_id=cls.dialog_id,
            class_name="w-fit h-fit",
        )


class InitializationDialogs(EventGroup):

    @staticmethod
    @rx.event
    async def initialize(state: OrbitLabState) -> FrontendEvents:
        state.status = InitializationStatus.IN_PROGRESS
        cluster = ClusterClient()
        backplane = BackplaneClient()
        
        if not await cluster.lan_network_configured():
            return [
                tailwind.Dialog.close(ErrorDialog.dialog_id),
                tailwind.Dialog.open(InitialConfigurationDialog.dialog_id)
            ]
        if not await backplane.exists():
            return [
                tailwind.Dialog.close(ErrorDialog.dialog_id),
                tailwind.Dialog.open(ConfigureBackplaneDialog.dialog_id)
            ]
        if not await cluster.defaults_exist():
            return [
                tailwind.Dialog.close(ErrorDialog.dialog_id),
                wait_for_default_settings,
            ]
        if not await cluster.infra_exists():
            return [
                tailwind.Dialog.close(ErrorDialog.dialog_id),
                download_infrastructure,
            ]
        if not await backplane.backplane_controller_exists():
            return [
                tailwind.Dialog.close(ErrorDialog.dialog_id),
                create_backplane_controller
            ]
        return [
            tailwind.Dialog.close(ErrorDialog.dialog_id),
            set_initialization_complete,
            rx.redirect("/")
        ]
    
    def __new__(cls) -> rx.Component:
        return rx.fragment(
            ErrorDialog(),
            InitialConfigurationDialog(),
            ConfigureBackplaneDialog(),
            ClusterSettingsDialog(),
        )
