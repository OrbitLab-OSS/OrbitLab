"""Proxmox Networking Client Models."""

import ipaddress
import re
from typing import Literal

from pydantic import BaseModel, Field, RootModel

from orbitlab.constants import NetworkSettings
from orbitlab.manifest.ipam import IpamManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.manifest.serialization import PeerList, PveBool


class AttachedInstances(BaseModel):
    """Represents an attached instance with its identification and network details."""

    vmid: str
    name: str
    ip: str


class ComputeConfig(BaseModel):
    """Represents a compute instance configuration."""

    hostname: str

    @property
    def is_orbitlab_infra(self) -> bool:
        """Check if this compute node is OrbitLab infrastructure."""
        return bool(re.match(pattern=r"olvn\d{4}gw", string=self.hostname))


class SectorAttachedInstances(BaseModel):
    """Represents a sector with its attached instances."""

    sector_id: str
    sector_name: str
    tag: int
    attached: list[AttachedInstances]

    @classmethod
    def create(cls, sector: SectorManifest, instances: dict[str, ComputeConfig]) -> "SectorAttachedInstances":
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


class Subnets(RootModel[list[Subnet]]):
    """A collection of Proxmox SDN subnets."""

    def get_backplane_subnet(self) -> Subnet:
        """Get the backplane subnet from the list of subnets."""
        return next(iter([subnet for subnet in self.root if subnet.id.startswith(NetworkSettings.BACKPLANE.NAME)]))


class ZoneBridgePorts(BaseModel):
    """Represents a Proxmox SDN zone bridge, which is a compute instance connected to the network."""

    name: str
    index: str | None = None
    vmid: str | None = None


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
        return self.root[0].ports
