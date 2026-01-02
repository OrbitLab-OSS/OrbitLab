"""Proxmox Networking Client Models."""

import ipaddress
import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel

from orbitlab.constants import NetworkSettings
from orbitlab.manifest.ipam import IpamManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.manifest.serialization import PeerList, PveBool


class AttachedInstances(BaseModel):
    """Represents an attached instance with its identification and network details."""

    vmid: int
    name: str
    ip: str


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

    @classmethod
    def create(cls, sector: SectorManifest, instances: dict[int, ComputeConfig]) -> "SectorAttachedInstances":
        """Create a SectorAttachedInstances object from sector and instance data."""
        ipam = IpamManifest.load(name=sector.spec.ipam.name)
        return cls.model_validate({
            "sector_id": sector.name,
            "sector_name": sector.metadata.alias,
            "tag": sector.metadata.tag,
            "attached": [
                {
                    "name": instance.hostname,
                    "vmid": vmid,
                    "ip": ipam.find_ip(vmid=vmid),
                }
                for vmid, instance in instances.items()
            ],
        })


class EVPNController(BaseModel):
    """Represents an EVPN controller configuration."""

    asn: int
    controller: str
    peers: PeerList

    @property
    def is_orbitlab_controller(self) -> bool:
        """Check if this controller is the OrbitLab backplane controller."""
        return self.controller == NetworkSettings.BACKPLANE.NAME


class BackplaneZone(BaseModel):
    """Represents a Proxmox SDN backplane zone configuration."""

    name: str = Field(alias="zone")
    type: Literal["evpn"]
    mtu: int
    tag: int = Field(alias="vrf-vxlan")
    advertise_subnets: PveBool = Field(alias="advertise-subnets")
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


class DescribeSector(BaseModel):
    vnet: VNet
    subnets: Subnets
    gateway_vmid: int
    assignments: dict[int, ipaddress.IPv4Interface]
