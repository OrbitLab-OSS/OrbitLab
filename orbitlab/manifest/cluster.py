"""OrbitLab Cluster Manifest Schema."""

from atexit import register
from ipaddress import IPv4Address, IPv4Network
from typing import Annotated

from pydantic import BaseModel, Field

from orbitlab import constants
from orbitlab.data_types import ClusterMode, ManifestKind, StorageContentType

from .ref import Ref
from .ipam import IpamManifest
from .nodes import NodeManifest
from .base import BaseManifest, Metadata, Spec
from .serialization import SerializeEnum, SerializeIP, SerializeIPList


class ClusterMetadata(Metadata):
    """Metadata for cluster manifest containing cluster-specific configuration."""

    initialized: bool = False
    mode: Annotated[ClusterMode, SerializeEnum]
    version: int
    quorate: bool
    mtu: int
    reserved_tags: list[int] = Field(default_factory=list)
    gateway_appliance: str = ""


class Controller(BaseModel):
    """Controller configuration for cluster networking."""

    id: str
    asn: int
    peers: Annotated[list[IPv4Address], SerializeIPList] = Field(default_factory=list)

    @property
    def peer_list(self) -> str:
        return ",".join([str(peer) for peer in self.peers])


class AssignedAddress(BaseModel):
    """Represents an assigned backplane IP address for a sector router."""

    network_id: str
    address: Annotated[IPv4Address, SerializeIP]


class Backplane(BaseModel):
    """Represents the backplane network configuration for the cluster."""

    zone_id: str
    vnet_id: str
    controller: Controller
    zone_tag: int
    vnet_tag: int
    mtu: int
    cidr_block: Annotated[IPv4Network, SerializeIP]
    gateway: Annotated[IPv4Address, SerializeIP]
    assignments: list[AssignedAddress] = Field(default_factory=list)

    def create_ipam_manifest(self) -> IpamManifest:
        """Create an IPAM manifest for the backplane network configuration."""
        return IpamManifest.model_validate({
            "name": constants.Backplane.IPAM,
            "metadata": {
                "network_name": constants.Backplane.ALIAS,
                "network_id": constants.Backplane.NAME,
            },
            "spec": {
                "subnets": [{
                    "name": constants.Backplane.NAME,
                    "cidr_block": self.cidr_block,
                }],
            },
        })


class Subnet(BaseModel):
    """Represents a subnet within a network configuration."""

    cidr_block: Annotated[IPv4Network, SerializeIP]
    name: str

    @property
    def gateway(self) -> IPv4Address:
        """Return the gateway IP address for this subnet (the first host IP address from the subnet's CIDR block)."""
        return next(iter(self.cidr_block.hosts()))


class DefaultStorageSelections(BaseModel):
    vztmpl: str = Field(default="")
    snippets: str = Field(default="")
    imports: str = Field(default="")
    iso: str = Field(default="")
    backups: str = Field(default="")
    rootdir: str = Field(default="")


class Defaults(BaseModel):
    storage: DefaultStorageSelections = DefaultStorageSelections()
    node: str = Field(default="")
    storage_profile: str = Field(default="")


class ClusterSpec(Spec):
    nodes: list[Ref] = Field(default_factory=list)
    backplane: Backplane
    sectors: dict[int, Ref] = Field(default_factory=dict)
    defaults: Defaults = Defaults()


class ClusterManifest(BaseManifest[ClusterMetadata, ClusterSpec]):
    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.CLUSTER

    @property
    def exit_nodes(self) -> str:
        """Return a comma-separated string of all cluster node names."""
        return ",".join([node.name for node in self.spec.nodes])

    def add_node(self, node: NodeManifest) -> None:
        self.spec.nodes.append(node.to_ref())
        self.spec.backplane.controller.peers.append(node.metadata.ip)
        self.save()

    def get_nodes(self) -> list[NodeManifest]:
        return [NodeManifest.load(name=node.name) for node in self.spec.nodes]

    def get_backplane(self) -> Backplane:
        if not self.spec.backplane:
            raise ValueError
        return self.spec.backplane

    def add_sector(self, tag: int, ref: Ref) -> None:
        self.spec.sectors[tag] = ref
        self.save()

    def remove_sector(self, tag: int) -> None:
        if tag in self.spec.sectors:
            del self.spec.sectors[tag]
            self.save()

    def get_next_available_tag(self, start: int = 1000, end: int = 9999) -> int:
        """Find the next available network tag in the range 1000-9999."""
        existing_tags = set(list(self.spec.sectors.keys()) + self.metadata.reserved_tags)
        try:
            return next(i for i in range(start, end + 1) if i not in existing_tags)
        except StopIteration as e:
            msg = f"There are no available tags between {start} and {end}."
            raise ValueError(msg) from e

    def get_storage_options(self, node: str, content_type: StorageContentType) -> list[str]:
        return [store.name for store in NodeManifest.load(name=node).spec.storage if content_type in store.content]
