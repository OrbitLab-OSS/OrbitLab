"""Proxmox Client Base Models."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime
import ipaddress
import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, RootModel, computed_field

from orbitlab import data_types


class Task(RootModel[str]):
    """Proxmox Task."""

    @property
    def upid(self) -> str:
        """Get the unique process identifier (UPID) of the task."""
        return self.root

    @property
    def node(self) -> str:
        """Get the node name from the UPID."""
        return self.root.split(":")[1]


class VMID(RootModel[int]):
    """Proxmox VM ID."""


class Storage(BaseModel):
    """Represents a storage resource in Proxmox."""

    type: data_types.PveStorageType
    active: data_types.PveBool
    content: data_types.PveContentList
    enabled: data_types.PveBool
    shared: data_types.PveBool
    name: str = Field(alias="storage")
    available_bytes: int = Field(alias="avail")
    total_bytes: int = Field(alias="total")
    used_bytes: int = Field(alias="used")
    utilization: float = Field(alias="used_fraction")


class ProxmoxStorages(RootModel[list[Storage]]):
    """Represents a collection of Proxmox storage resources with utility methods."""

    def list_all(self) -> list[str]:
        """Return a list of all storage names."""
        return [store.name for store in self.root]


class ProxmoxTaskError(Exception):
    """"""


class ProxmoxTaskStatus(BaseModel):
    """Represents the status of a Proxmox task."""

    start_time: Annotated[int, Field(alias="starttime")]
    pid: int
    node: str
    pstart: int
    type: str
    upid: str
    status: data_types.TaskStatus
    id: str
    user: str
    exit_status: Annotated[str | None, Field(alias="exitstatus", default=None)]
    
    def raise_for_status(self) -> None:
        if self.exit_status != "OK":
            raise ProxmoxTaskError(self.exit_status)


class ContentItem(BaseModel):
    """Represents a content item in Proxmox storage."""

    id: Annotated[str, Field(alias="volid")]
    content_type: Annotated[data_types.StorageContentType, Field(alias="content")]
    format: str
    size_bytes: Annotated[int, Field(alias="size")]
    creation_time: Annotated[int, Field(alias="ctime")]


ProxmoxStorageContent = RootModel[list[ContentItem]]


class ProxmoxTermProxy(BaseModel):
    """Represents Proxmox terminal proxy configuration for VNC connections."""

    port: int
    ticket: str
    upid: str
    user: str

    def to_params(self) -> dict[str, int | str]:
        """Convert the terminal proxy data to a dictionary of parameters."""
        return {"port": self.port, "vncticket": self.ticket}


class AuthData(BaseModel):
    """Represents authentication data returned by Proxmox API."""

    csrf_prevention_token: Annotated[str, Field(alias="CSRFPreventionToken")]
    cookie: Annotated[str, Field(alias="ticket")]


class ProxmoxAuth(BaseModel):
    """Represents Proxmox authentication response."""

    data: AuthData
    
    @classmethod
    def from_pvesh(cls, data: str) -> Self:
        return cls(data=AuthData.model_validate_json(data))


class ProxmoxComputeResource(BaseModel):
    name: str = ""
    node: str
    status: str
    type: Literal["lxc", "qemu"]
    vmid: int


class ProxmoxComputeResources(RootModel[list[ProxmoxComputeResource]]):
    def get_resource(self, vmid: int) -> ProxmoxComputeResource:
        return next(iter(resource for resource in self.root if resource.vmid == vmid))


class VMClusterResource(BaseModel):
    """Represents a VM cluster resource with its VM ID and node name."""

    vmid: int
    node: str


class VMClusterResources(RootModel[list[VMClusterResource]]):
    """Represents a collection of VM cluster resources with utility methods."""

    def get_node(self, vmid: int) -> str:
        """Get the node name for a given VM ID."""
        return next(iter(vm.node for vm in self.root if vm.vmid == vmid), "")


class ProxmoxNode(BaseModel):
    """Represents the status of a Proxmox cluster node."""

    type: Literal["node"]
    node_id: Annotated[int, Field(alias="nodeid")]
    local: data_types.PveBool
    online: data_types.PveBool
    ip: ipaddress.IPv4Address
    name: str


class ProxmoxCluster(BaseModel):
    """Represents the status of a Proxmox cluster."""

    type: Literal["cluster"]
    name: str
    quorate: bool
    version: int
    nodes: int


class ProxmoxClusterStatus(RootModel[list[Annotated[ProxmoxCluster | ProxmoxNode, Field(discriminator="type")]]]):
    """Represents the status of a Proxmox cluster including nodes and cluster information."""

    def list_nodes(self) -> list[ProxmoxNode]:
        """Get all nodes from the cluster status."""
        return [item for item in self.root if isinstance(item, ProxmoxNode)]

    def get_node(self, node: str) -> ProxmoxNode:
        return next(iter([item for item in self.root if isinstance(item, ProxmoxNode) and item.name == node]))

    def get_local_node(self) -> str:
        """Get the name of the local node from the cluster status."""
        return next(iter(node.name for node in self.list_nodes() if node.local))

    def get_cluster(self) -> ProxmoxCluster | None:
        """Get the cluster status from the cluster status list."""
        return next(iter(item for item in self.root if isinstance(item, ProxmoxCluster)), None)


class ProxmoxBridge(BaseModel):
    active: data_types.PveBool
    address: ipaddress.IPv4Address
    autostart: data_types.PveBool
    cidr: ipaddress.IPv4Interface
    iface: str


class ProxmoxBridges(RootModel[list[ProxmoxBridge]]):
    def get_vmbr0(self) -> ProxmoxBridge:
        return next(iter(bridge for bridge in self.root if bridge.iface == "vmbr0"))


class ProxmoxVnet(BaseModel):
    vnet: str
    tag: int = 0
    pending: dict | None = None
    alias: str = ""
    zone: str = ""


class ProxmoxVnets(RootModel[list[ProxmoxVnet]]):
    def get_used_tags(self) -> list[int]:
        """Return configured and pending VLAN tags reported by PVE."""
        tags: list[int] = []
        for vnet in self.root:
            if vnet.tag:
                tags.append(vnet.tag)
                continue
            if vnet.pending and "tag" in vnet.pending:
                tags.append(int(vnet.pending["tag"]))
        return tags

    def get_all_tags(self) -> list[int]:
        """Compatibility name used by network allocation callers."""
        return self.get_used_tags()


class QemuConfig(BaseModel):
    """Represents QEMU configuration for a compute instance."""

    agent: str
    scsi0: str

    @property
    def agent_enabled(self) -> bool:
        """If the Qemu Guest Agent is enabled on the VM."""
        return self.agent == "enabled=1"

    @property
    def root_volume_id(self) -> str:
        volume_id, _ = self.scsi0.split(",")
        return volume_id


class AgentExecStatus(BaseModel):
    """Represents the execution status of an agent command in Proxmox."""

    exited: data_types.PveBool
    stderr: str = Field(alias="err-data", default="")
    stdout: str = Field(alias="out-data", default="")
    exitcode: int | None = None
    signal: int | None = None

    @property
    def logs(self) -> list[str]:
        """Return combined non-empty lines from stdout and stderr as a list of log entries."""
        formatted_logs = [line for line in self.stdout.split("\n") if line]
        formatted_logs.extend([line for line in self.stderr.split("\n") if line])
        return formatted_logs

    def __bool__(self) -> bool:
        return self.exitcode is not None


class AgentExecPid(BaseModel):
    """Represents the process ID of an agent execution in Proxmox."""

    pid: int


class HANode(BaseModel):
    """Represents a High Availability node in a Proxmox cluster."""

    id: str
    node: str
    quorate: data_types.PveBool
    status: str
    type: str


class CurrentHAStatus(RootModel[list[HANode]]):
    """Represents the current High Availability status of Proxmox nodes."""

    def in_maintenance_mode(self, node: str) -> bool:
        """Check if a node is in maintenance mode."""
        for ha_node in self.root:
            if ha_node.node == node:
                return "maintenance" in ha_node.status
        raise ValueError


class StorageResource(BaseModel):
    """Represents a storage resource in the Proxmox cluster."""

    content: data_types.PveContentList
    id: str
    node: str
    plugintype: str
    shared: data_types.PveBool
    status: str
    storage: str


class StorageResources(RootModel[list[StorageResource]]):
    """List of StorageResource objects."""

    def get_storage_for_node(self, node: str) -> list[dict]:
        """Get storage resources in NodeManifest format for a specific node."""
        return [
            {
                "name": store.storage,
                "content": store.content,
                "shared": store.shared,
            }
            for store in self.root if store.node == node
        ]


class VendoredImage(BaseModel):
    """Represents an asset from a software release."""

    filename: str
    digest: str
    size: int
    download_url: Annotated[str, Field(alias="browser_download_url")]

    @computed_field
    @property
    def os(self) -> str:
        """Return a human-readable formatted name for the asset."""
        os_type, os_version, arch, _ = self.filename.split("-")
        return f"{os_type.capitalize()} {os_version} {arch}"

    @computed_field
    @property
    def build_date(self) -> str:
        """Return the build date extracted from the asset name."""
        _, _, _, build_date_and_filetype = self.filename.split("-")
        build_date, _ = build_date_and_filetype.split(".")
        return build_date

    @computed_field
    @property
    def checksum(self) -> str:
        _, checksum = self.digest.split(":")
        return checksum

    @computed_field
    @property
    def checksum_algorithm(self) -> str:
        checksum_algorithm, _ = self.digest.split(":")
        return checksum_algorithm


class VendoredImages(BaseModel):
    """Represents a collection of released image assets."""

    images: list[VendoredImage]

    def get_os_image(self, os: str) -> VendoredImage:
        """Return the asset object for the OS image with the given formatted name."""
        return next(iter(img for img in self.images if img.os == os))


class IpAddress(BaseModel):
    """Represents an IP address with its type, prefix, and value."""

    address_type: Literal["inet", "inet6", "ipv4", "ipv6"] = Field(alias="ip-address-type")
    prefix: str | int
    address: str = Field(alias="ip-address")


class Interfaces(ABC):
    
    @abstractmethod
    def get_ipv4(self, device: str) -> ipaddress.IPv4Interface | None: ...


class LXCInterface(BaseModel):
    """Represents a LXC network interface with hardware address, name, and associated IP addresses."""

    hwaddr: str | None = None
    name: str
    ip_addresses: list[IpAddress] = Field(alias="ip-addresses")

    def get_ipv4_interface(self) -> ipaddress.IPv4Interface | None:
        """Return the IPv4 interface object for the first IPv4 address found."""
        ip = next(iter(addr for addr in self.ip_addresses if addr.address_type == "inet"), None)
        if ip:
            return ipaddress.IPv4Interface(address=f"{ip.address}/{ip.prefix}")
        return None


class LXCInterfaces(RootModel[list[LXCInterface]]):
    """Represents a collection of LXC network interfaces."""

    def get_ipv4(self, device: str) -> ipaddress.IPv4Interface | None:
        """Return the IPv4 interface object for the default 'eth0' network interface."""
        interface = next(iter([dev for dev in self.root if dev.name == device]), None)
        if interface:
            return interface.get_ipv4_interface()
        return None


class VMInterface(BaseModel):
    """Represents a VM network interface with its name and associated IP addresses."""

    name: str
    ip_addresses: list[IpAddress] = Field(alias="ip-addresses")

    def get_ipv4_interface(self) -> ipaddress.IPv4Interface | None:
        """Return the IPv4 interface object for the first IPv4 address found."""
        ip = next(iter(addr for addr in self.ip_addresses if addr.address_type == "ipv4"), None)
        if ip:
            return ipaddress.IPv4Interface(address=f"{ip.address}/{ip.prefix}")
        return None


class VMInterfaces(BaseModel):
    """Represents a collection of VM network interfaces."""

    result: list[VMInterface]

    def get_ipv4(self, device: str) -> ipaddress.IPv4Interface | None:
        """Return the IPv4 interface object for the default 'eth0' network interface."""
        interface = next(iter([dev for dev in self.result if dev.name == device]), None)
        if interface:
            return interface.get_ipv4_interface()
        return None


class InstanceStatus(BaseModel):
    """Represents the status of a compute instance."""

    status: Literal["stopped", "running"]
    vmid: int
    name: str


class VMVolume(BaseModel):
    volume_id: str
    size: str

    @classmethod
    def from_config_string(cls, value: str) -> Self:
        storage, extra = value.split(":")
        disk, size = extra.split(",")
        _, disk_name = disk.split("/")
        return cls(
            storage=storage,
            disk_name=disk_name,
            size=size.replace("size=", "")
        )


class ProxmoxPool(BaseModel):
    pool_id: str = Field(alias="poolid")
    comment: str


class ProxmoxPools(RootModel[list[ProxmoxPool]]):
    
    def get_pool_by_alias(self, alias: str) -> ProxmoxPool | None:
        return next(iter([pool for pool in self.root if pool.comment == alias]), None)

    def get_pool_by_id(self, pool_id: str) -> ProxmoxPool | None:
        return next(iter([pool for pool in self.root if pool.pool_id == pool_id]), None)


class ApplianceInfo(BaseModel):
    """Represents information about a Proxmox appliance."""

    architecture: str
    description: str
    headline: str
    info_page: Annotated[str, Field(alias="infopage")]
    location: str
    os: str
    package: str
    section: str
    sha512sum: str
    source: str
    template: str
    type: str
    version: str

    maintainer: Annotated[str | None, Field(default=None)]
    md5sum: Annotated[str | None, Field(default=None)]
    manage_url: Annotated[str | None, Field(alias="manageurl", default=None)]

    @property
    def is_turnkey(self) -> bool:
        """Indicates whether the appliance is a TurnKey appliance based on the presence of a management URL."""
        return bool(self.manage_url)


class Appliances(RootModel[list[ApplianceInfo]]):
    """Proxmox Appliances."""

    def system_appliances(self) -> list[ApplianceInfo]:
        """Return a list of system appliances (non-TurnKey appliances)."""
        return [apl for apl in self.root if not apl.is_turnkey]

    def turnkey_appliances(self) -> list[ApplianceInfo]:
        """Return a list of TurnKey appliances."""
        return [apl for apl in self.root if apl.is_turnkey]


class OrbitLabAppliance(BaseModel):

    filename: str
    digest: str
    size: int
    browser_download_url: str


class OrbitLabAppliances(BaseModel):
    """Represents the latest release information from the repository metadata."""

    version: str
    published_at: datetime
    appliances: list[OrbitLabAppliance]

    def get_appliance(self, appliance_type: data_types.OrbitLabApplianceType) -> OrbitLabAppliance:
        return next(appliance for appliance in self.appliances if appliance.filename.startswith(f"orbitlab-{appliance_type}"))


class StoredAppliance(BaseModel):
    """Represents a stored appliance template in Proxmox storage."""

    volid: str
    size: int
    format: str
    ctime: int

    @property
    def is_orbitlab_appliance(self) -> bool:
        """Check if this is an OrbitLab appliance based on the volume ID."""
        return "orbitlab-" in self.volid


class StoredAppliances(RootModel[list[StoredAppliance]]):
    """A list of stored appliances."""

    def __iter__(self) -> Iterator[StoredAppliance]:
        """Return an iterator over the stored appliances."""
        return iter([i for i in self.root if not i.is_orbitlab_appliance])

    def get_appliance(self, filename: str) -> StoredAppliance:
        appliance = next(iter([i for i in self.root if filename in i.volid]), None)
        if not appliance:
            msg = f"Appliance containing '{filename}' not found."
            raise ValueError(msg)
        return appliance

    def template_exists(self, template: str) -> bool:
        """Check if an appliance template exists in the stored appliances."""
        return bool(next(iter([i for i in self.root if template in i.volid]), None))


class StoredImage(BaseModel):
    """Represents a stored VM image in Proxmox storage."""

    volid: str
    size: int
    format: str
    ctime: int

    @property
    def image_name(self) -> str:
        """Get the image name from the volume ID by extracting the part after 'import/'."""
        return self.volid.split("import/")[-1]

    @property
    def storage(self) -> str:
        """Get the storage identifier from the volume ID."""
        return self.volid.split(":vztmpl")[0]


class StoredImages(RootModel[list[StoredImage]]):
    """A list of stored appliances."""

    def __iter__(self) -> Iterator[StoredImage]:
        """Return an iterator over the stored images."""
        return iter(self.root)

    def get_image(self, filename: str) -> StoredImage:
        return next(iter([i for i in self.root if filename in i.volid]))

    def image_exists(self, image: str) -> bool:
        """Check if an appliance template exists in the stored image."""
        return bool(next(iter([i for i in self.root if i.image_name == image]), None))


class VolumeContentInfo(BaseModel):
    """Represents information about the content of a volume in Proxmox storage."""

    format: str
    path: str
    size: int
    used: int



class AttachedInstances(BaseModel):
    """Represents an attached instance with its identification and network details."""

    vmid: int
    compute_type: str


class ComputeConfig(BaseModel):
    """Represents a compute instance configuration."""

    hostname: str
    net0: str

    @property
    def is_orbitlab_infra(self) -> bool:
        """Check if this compute node is OrbitLab infrastructure."""
        if re.match(pattern=r"olvn\d{4}-gw", string=self.hostname):
            return True
        return bool(re.match(pattern=r"olvn\d{4}-dns", string=self.hostname))

    def get_sector_address(self, network: ipaddress.IPv4Network) -> ipaddress.IPv4Interface | None:
        ip = next(iter(i for i in self.net0.split(",") if i.startswith("ip")), None)
        if ip:
            _, str_addr = ip.split("=")
            address = ipaddress.IPv4Interface(str_addr)
            if address in network:
                return address
        return None


class SectorAttachedInstances(BaseModel):
    """Represents a sector with its attached instances."""

    sector_id: str
    sector_name: str
    tag: int
    attached: list[AttachedInstances]

    # @classmethod
    # def create(cls, sector: SectorManifest, instances: dict[int, ComputeConfig]) -> "SectorAttachedInstances":
    #     """Create a SectorAttachedInstances object from sector and instance data."""
    #     return cls.model_validate({
    #         "sector_id": sector.name,
    #         "sector_name": sector.metadata.alias,
    #         "tag": sector.metadata.tag,
    #         "attached": [
    #             {
    #                 "name": instance.hostname,
    #                 "vmid": vmid,
    #             }
    #             for vmid, instance in instances.items()
    #         ],
    #     })


class EVPNController(BaseModel):
    """Represents an EVPN controller configuration."""

    type: Literal["evpn"]
    asn: int
    controller: str
    peers: data_types.PeerList


class BGPController(BaseModel):
    type: Literal["bgp"]
    controller: str
    asn: int


class IsIsController(BaseModel):
    type : Literal["isis"]


class SDNControllers(RootModel[list[Annotated[EVPNController | BGPController | IsIsController, Field(discriminator="type")]]]):
    def get_all_asns(self) -> list[int]:
        return [controller.asn for controller in self.root if isinstance(controller, EVPNController | BGPController)]

    def get_evpn_controller(self) -> EVPNController | None:
        return next(iter(controller for controller in self.root if isinstance(controller, EVPNController)), None)



class BackplaneZone(BaseModel):
    """Represents a Proxmox SDN backplane zone configuration."""

    name: str = Field(alias="zone")
    type: Literal["evpn"]
    mtu: int
    tag: int = Field(alias="vrf-vxlan")
    advertise_subnets: data_types.PveBool = Field(alias="advertise-subnets")
    controller: str
    exit_nodes: str = Field(alias="exitnodes")


class VNet(BaseModel):
    """Represents a Proxmox backplane virtual network configuration."""

    name: str = Field(alias="vnet")
    type: Literal["vnet"]
    zone: str
    alias: str
    tag: int


class VNetList(RootModel[list[VNet]]):
    """List of VNet objects."""

    def sector_exists(self, tag: int) -> bool:
        """Check if a sector with a given VLAN tag exists."""
        return bool(next(iter([net for net in self.root if net.tag == tag]), None))

    def get_all_tags(self) -> list[int]:
        """Get all currently used VLAN tags."""
        return [net.tag for net in self.root]


class Subnet(BaseModel):
    """Represents a Proxmox SDN subnet."""

    type: Literal["subnet"]
    cidr: ipaddress.IPv4Network
    gateway: ipaddress.IPv4Address
    id: str
    mask: str
    network: ipaddress.IPv4Address
    subnet: str
    vnet: str
    zone: str

    @property
    def gateway_interface(self) -> ipaddress.IPv4Interface:
        return ipaddress.IPv4Interface(f"{self.gateway}/{self.mask}")


class Subnets(RootModel[list[Subnet]]):
    def get_first(self) -> Subnet:
        return next(iter(self.root))

    def get_cidr(self) -> ipaddress.IPv4Network:
        return next(ipaddress.collapse_addresses([subnet.cidr for subnet in self.root]))


class VNetSectorConfig(BaseModel):
    vnet: VNet
    subnets: Subnets
    backplane_ip: ipaddress.IPv4Interface
    gw_vmid: int


class ZoneBridgePorts(BaseModel):
    """Represents a Proxmox SDN zone bridge, which is a compute instance connected to the network."""

    name: str
    index: str | None = None
    vmid: int | None = None

    @property
    def compute_type(self) -> Literal["lxc", "qemu"]:
        """Return the compute type based on the bridge port name."""
        if self.name.startswith("veth"):
            return "lxc"
        return "qemu"


class ZoneBridge(BaseModel):
    """Represents a Proxmox SDN zone bridge configuration."""

    name: str
    ports: list[ZoneBridgePorts]


class ZoneBridges(RootModel[list[ZoneBridge]]):
    """A collection of zone bridges."""

    def get_vms(self) -> list[ZoneBridgePorts]:
        """Get the list of VM ports from the first zone bridge."""
        if not self.root:
            return []
        return [i for i in self.root[0].ports if i.vmid]


class EVPNZone(BaseModel):
    type: Literal["evpn"] = "evpn"
    controller: str
    exitnodes: str
    mtu: int
    tag: int = Field(alias="vrf-vxlan")
    zone: str


class VXLANZone(BaseModel):
    type: Literal["vxlan"] = "vxlan"
    zone: str


class ClusterVMResource(BaseModel):
    id: str
    name: str
    node: str
    type: str
    vmid: int

    @property
    def is_gateway(self) -> bool:
        return all([self.name.startswith("olvn"), self.name.endswith("gw")])


class ClusterVMResources(RootModel[list[ClusterVMResource]]):
    def list_gateways(self) -> list[ClusterVMResource]:
        return [vm for vm in self.root if vm.is_gateway]
    
    def list_non_gw_vms(self) -> list[ClusterVMResource]:
        return [vm for vm in self.root if not vm.is_gateway]
    

class LXCConfig(BaseModel):
    net0: str
    net1: str

    @property
    def vnet_id(self) -> str:
        return self.net1.split(",")[1].split("=")[-1]

    @property
    def backplane_ip(self) -> ipaddress.IPv4Interface:
        return ipaddress.IPv4Interface(self.net1.split(",")[4].split("=")[-1])


class DescribeBackplane(BaseModel):
    zone: BackplaneZone
    vnet: VNet
    controller: EVPNController
    subnet: Subnet


class SectorZone(BaseModel):
    fabric: str
    mtu: int


class DescribeSector(BaseModel):
    zone: SectorZone
    subnets: Subnets
    gateway_vmid: int
    assignments: dict[int, ipaddress.IPv4Interface]
