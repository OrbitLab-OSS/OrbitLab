"""Models for representing Proxmox nodes, SDN zones, subnets, DHCP ranges, and network interfaces.

This module defines Pydantic models for Proxmox-related resources,
with appropriate type annotations and field aliases for serialization and validation.
"""

import ipaddress
from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel, computed_field

from orbitlab import data_types
from orbitlab.manifest.schemas.serialization import PveBool, PveContentList, PveStorageType


class NodeInfo(BaseModel):
    """Represents a Proxmox node with its status and resource information.

    Attributes:
        name (str): The name of the node (aliased as "node").
        status (NodeStatus): The status of the node.
        uptime (int | None): The uptime of the node in seconds.
        ssl_fingerprint (str): The SSL fingerprint of the node.
        cpu_utilization (float | None): The CPU utilization (aliased as "cpu").
        total_cpus (int | None): The total number of CPUs (aliased as "maxcpu").
        total_memory (int | None): The total memory in bytes (aliased as "maxmem").
        used_memory (int | None): The used memory in bytes (aliased as "mem").
    """

    name: Annotated[str, Field(alias="node")]
    status: data_types.NodeStatus
    uptime: int | None = None
    ssl_fingerprint: str
    cpu_utilization: Annotated[float | None, Field(alias="cpu", default=None)]
    total_cpus: Annotated[int | None, Field(alias="maxcpu", default=None)]
    total_memory: Annotated[int | None, Field(alias="maxmem", default=None)]
    used_memory: Annotated[int | None, Field(alias="mem", default=None)]

    @computed_field
    @property
    def total_mem_gb(self) -> int:
        """Calculate total memory in gigabytes.

        Returns:
            int: The total memory converted from bytes to gigabytes.
        """
        return int(self.total_memory / (1024**3))


ProxmoxNodes = RootModel[list[NodeInfo]]


class ProxmoxSDNZone(BaseModel):
    """Represents a Proxmox SDN zone configuration.

    Attributes:
        zone_type (data_types.ZoneTypes): The type of the SDN zone.
        zone_name (str): The name of the SDN zone.
        mac (str): The MAC address associated with the zone.
        mtu (int): The MTU size for the zone.
        controller (str | None): The controller for the zone, if any.
    """

    zone_type: Annotated[data_types.ZoneTypes, Field(alias="type")]
    zone_name: Annotated[str, Field(alias="zone")]
    mac: str
    mtu: int
    controller: str | None = None


class DHCPRange(BaseModel):
    """Represents a DHCP range with start and end IPv4 addresses.

    Attributes:
        start (ipaddress.IPv4Address): The starting IPv4 address of the DHCP range.
        end (ipaddress.IPv4Address): The ending IPv4 address of the DHCP range.
    """

    start: Annotated[ipaddress.IPv4Address, Field(alias="start-address")]
    end: Annotated[ipaddress.IPv4Address, Field(alias="end-address")]


class ProxmoxSDNSubnet(BaseModel):
    """Represents a Proxmox SDN subnet configuration.

    Attributes:
        dns_prefix (str): The DNS zone prefix for the subnet.
        gateway (ipaddress.IPv4Address): The gateway IP address for the subnet.
        cidr_block (ipaddress.IPv4Network): The CIDR block of the subnet.
        dhcp_ranges (list[DHCPRange]): List of DHCP ranges within the subnet.
    """

    dns_prefix: Annotated[str, Field(alias="dnszoneprefix")]
    gateway: ipaddress.IPv4Address
    cidr_block: Annotated[ipaddress.IPv4Network, Field(alias="cidr")]
    dhcp_ranges: Annotated[list[DHCPRange], Field(alias="dhcp-range")]


class Network(BaseModel):
    """Represents a Proxmox network interface and its configuration.

    Attributes:
        active (PveBool | None): Whether the network is active.
        autostart (PveBool | None): Whether the network is set to autostart.
        interface_type (data_types.NetworkTypes): The type of network interface.
        interface_name (str): The name of the network interface.
        physical_interface (PveBool): Whether the interface exists physically.
        ipv4_method (data_types.NetworkMethods): The IPv4 configuration method.
        ipv4_address (ipaddress.IPv4Address | None): The IPv4 address.
        ipv6_method (data_types.NetworkMethods): The IPv6 configuration method.
        ipv6_address (ipaddress.IPv4Address | None): The IPv6 address.
        cidr (ipaddress.IPv4Interface | None): The CIDR block for the interface.
        gateway (ipaddress.IPv4Address | None): The gateway address.
        comment (str): Any comments associated with the network.
        bridge_ports (str | None): Bridge ports if applicable.
    """

    active: PveBool | None = None
    autostart: PveBool | None = None
    interface_type: Annotated[data_types.NetworkTypes, Field(alias="type")]
    interface_name: Annotated[str, Field(alias="iface")]
    physical_interface: Annotated[PveBool, Field(alias="exists", default=False)]
    ipv4_method: Annotated[data_types.NetworkMethods, Field(alias="method")]
    ipv4_address: Annotated[ipaddress.IPv4Address | None, Field(alias="address", default=None)]
    ipv6_method: Annotated[data_types.NetworkMethods, Field(alias="method6")]
    ipv6_address: Annotated[ipaddress.IPv4Address | None, Field(alias="address6", default=None)]
    cidr: ipaddress.IPv4Interface | None = None
    gateway: ipaddress.IPv4Address | None = None
    comment: str = ""
    bridge_ports: str | None = None


ProxmoxNetworks = RootModel[list[Network]]


class Storage(BaseModel):
    """
    Represents a storage resource in Proxmox.

    Attributes:
        type (PveStorageType): The type of storage.
        active (PveBool): Whether the storage is active.
        content (PveContentList): List of content types supported.
        enabled (PveBool): Whether the storage is enabled.
        shared (PveBool): Whether the storage is shared.
        name (str): The name of the storage (aliased as 'storage').
        available_bytes (int): Available bytes (aliased as 'avail').
        total_bytes (int): Total bytes (aliased as 'total').
        used_bytes (int): Used bytes (aliased as 'used').
        utilization (float): Utilization ratio.
    """

    type: PveStorageType
    active: PveBool
    content: PveContentList
    enabled: PveBool
    shared: PveBool
    name: Annotated[str, Field(alias="storage")]
    available_bytes: Annotated[int, Field(alias="avail")]
    total_bytes: Annotated[int, Field(alias="total")]
    used_bytes: Annotated[int, Field(alias="used")]
    utilization: Annotated[float, Field(alias="used_fraction")]


ProxmoxStorages = RootModel[list[Storage]]


class ApplianceInfo(BaseModel):
    """Represents information about a Proxmox appliance.

    Attributes:
        architecture (str): The architecture of the appliance.
        description (str): Description of the appliance.
        headline (str): Headline for the appliance.
        info_page (str): URL to the info page (aliased as 'infopage').
        location (str): Location of the appliance.
        os (str): Operating system of the appliance.
        package (str): Package name.
        section (str): Section of the appliance.
        sha512sum (str): SHA512 checksum.
        source (str): Source of the appliance.
        template (str): Template name.
        type (str): Type of the appliance.
        version (str): Version of the appliance.
        maintainer (str | None): Maintainer of the appliance.
        md5sum (str | None): MD5 checksum.
        manage_url (str | None): Management URL (aliased as 'manageurl').
    """

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
        """Indicates whether the appliance is a TurnKey appliance based on the presence of a management URL.

        Returns:
            bool: True if the appliance has a management URL, indicating it is a TurnKey appliance; False otherwise.
        """
        return bool(self.manage_url)


ProxmoxAppliances = RootModel[list[ApplianceInfo]]


class ProxmoxTaskStatus(BaseModel):
    """Represents the status of a Proxmox task.

    Attributes:
        start_time (int): The start time of the task (aliased as 'starttime').
        pid (int): The process ID of the task.
        node (str): The node on which the task is running.
        pstart (int): The parent start time.
        type (str): The type of the task.
        upid (str): The unique process ID.
        status (data_types.TaskStatus): The status of the task.
        id (str): The identifier of the task.
        user (str): The user who initiated the task.
        exit_status (str | None): The exit status of the task (aliased as 'exitstatus').
    """

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


class NodeStatus(BaseModel):
    node_id: Annotated[int, Field(alias="nodeid")]
    local: PveBool
    online: PveBool
    type: Literal["node"]
    ip: ipaddress.IPv4Address | None = None
    name: str


class ClusterStatus(BaseModel):
    name: str
    quorate: PveBool
    type: Literal["cluster"]
    quorate: bool
    version: int
    nodes: int


ClusterItem = Annotated[ClusterStatus | NodeStatus, Field(discriminator="type")]

ProxmoxClusterStatus = RootModel[list[ClusterItem]]
