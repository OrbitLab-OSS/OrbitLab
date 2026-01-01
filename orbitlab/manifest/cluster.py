"""OrbitLab Cluster Manifest Schema."""

from ipaddress import IPv4Address, IPv4Interface, IPv4Network
from typing import Annotated, Self

from pydantic import BaseModel, Field

from orbitlab import constants
from orbitlab.clients.proxmox.cluster.models import ClusterStatus
from orbitlab.data_types import ClusterMode, ManifestKind, StorageContentType, StorageProfile

from .base import BaseManifest, Metadata, Spec
from .ipam import IpamManifest
from .nodes import NodeManifest
from .ref import Ref
from .serialization import SerializeEnum, SerializeIP, SerializeIPList


class ClusterMetadata(Metadata):
    """Metadata for cluster manifest containing cluster-specific configuration."""

    initialized: bool = False
    mode: Annotated[ClusterMode, SerializeEnum]
    version: int
    quorate: bool
    mtu: int
    reserved_tags: list[int] = Field(default_factory=list)
    sector_gateway_appliance: str = ""
    sector_dns_appliance: str = ""
    backplane_dns_appliance: str = ""


class Controller(BaseModel):
    """Controller configuration for cluster networking."""

    id: str
    asn: int
    peers: Annotated[list[IPv4Address], SerializeIPList] = Field(default_factory=list)

    @property
    def peer_list(self) -> str:
        """Return a comma-separated string of peer IP addresses."""
        return ",".join([str(peer) for peer in self.peers])


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

    def create_ipam_manifest(self) -> None:
        """Create an IPAM manifest for the backplane network configuration."""
        IpamManifest.model_validate(
            {
                "name": constants.Backplane.IPAM,
                "metadata": {
                    "sector_name": constants.Backplane.ALIAS,
                    "sector_id": constants.Backplane.NAME,
                },
                "spec": {
                    "subnets": [
                        {
                            "name": constants.Backplane.NAME,
                            "cidr_block": self.cidr_block,
                        },
                    ],
                },
            },
        ).save()


class DefaultStorageSelections(BaseModel):
    """Default storage selections for various content types in the cluster."""

    vztmpl: str = Field(default="")
    snippets: str = Field(default="")
    imports: str = Field(default="")
    iso: str = Field(default="")
    backup: str = Field(default="")
    rootdir: str = Field(default="")
    images: str = Field(default="")


class Defaults(BaseModel):
    """Default configuration settings for the cluster."""

    storage: DefaultStorageSelections = DefaultStorageSelections()
    node: str = Field(default="")
    storage_profile: Annotated[StorageProfile, SerializeEnum] = Field(default=StorageProfile.LOCAL)


class ClusterSpec(Spec):
    """Specification for an OrbitLab cluster."""

    nodes: list[Ref] = Field(default_factory=list)
    backplane: Backplane
    sectors: dict[int, Ref] = Field(default_factory=dict)
    defaults: Defaults = Defaults()


class ClusterManifest(BaseManifest[ClusterMetadata, ClusterSpec]):
    """Manifest schema for an OrbitLab cluster."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.CLUSTER

    @property
    def exit_nodes(self) -> str:
        """Return a comma-separated string of all cluster node names."""
        return ",".join([node.name for node in self.spec.nodes])

    def assign_ip(self, vmid: int) -> IPv4Interface:
        """Assign an IP address to the given VMID using the backplane IPAM manifest."""
        return IpamManifest.load(name=constants.NetworkSettings.BACKPLANE.IPAM).assign_ip(
            subnet_name=constants.NetworkSettings.BACKPLANE.NAME,
            vmid=vmid,
        )

    def get_assigned_ip(self, vmid: int) -> IPv4Interface:
        """Retrieve the assigned IP address for the given VMID from the backplane IPAM manifest."""
        assignment = IpamManifest.load(name=constants.NetworkSettings.BACKPLANE.IPAM).get_assigned_ip(
            subnet_name=constants.NetworkSettings.BACKPLANE.NAME,
            vmid=vmid,
        )
        if not assignment:
            raise ValueError
        return assignment

    def release_ip(self, vmid: int) -> None:
        """Release the IP address assigned to the given VMID using the backplane IPAM manifest."""
        IpamManifest.load(name=constants.NetworkSettings.BACKPLANE.IPAM).release_ip(
            subnet_name=constants.NetworkSettings.BACKPLANE.NAME,
            vmid=vmid,
        )

    def add_node(self, node: NodeManifest) -> None:
        """Add a node to the cluster and update the backplane controller peers."""
        self.spec.nodes.append(node.to_ref())
        self.spec.backplane.controller.peers.append(node.metadata.ip)
        self.save()

    def list_nodes(self) -> list[str]:
        """Return a list of node names in this cluster."""
        return [node.name for node in self.spec.nodes]

    def get_nodes(self) -> list[NodeManifest]:
        """Return a list of all NodeManifest objects for nodes in this cluster."""
        return [NodeManifest.load(name=node.name) for node in self.spec.nodes]

    def default_node(self) -> NodeManifest:
        """Get the default node for the cluster."""
        return NodeManifest.load(name=self.spec.defaults.node)

    def add_sector(self, tag: int, ref: Ref) -> None:
        """Add a sector to the cluster with the specified tag."""
        self.spec.sectors[tag] = ref
        self.save()

    def remove_sector(self, tag: int) -> None:
        """Remove a sector from the cluster by its tag."""
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

    def get_storage(self, content_type: StorageContentType) -> str:
        """Get the storage location for a specific content type."""
        match content_type:
            case StorageContentType.VZTMPL:
                storage = self.spec.defaults.storage.vztmpl or self.default_node().get_storage(
                    content_type=StorageContentType.VZTMPL,
                )
            case StorageContentType.ROOTDIR:
                storage = self.spec.defaults.storage.rootdir or self.default_node().get_storage(
                    content_type=StorageContentType.ROOTDIR,
                )
            case StorageContentType.IMAGES:
                storage = self.spec.defaults.storage.images or self.default_node().get_storage(
                    content_type=StorageContentType.IMAGES,
                )
            case StorageContentType.SNIPPETS:
                storage = self.spec.defaults.storage.snippets or self.default_node().get_storage(
                    content_type=StorageContentType.SNIPPETS,
                )
            case StorageContentType.ISO:
                storage = self.spec.defaults.storage.iso or self.default_node().get_storage(
                    content_type=StorageContentType.ISO,
                )
            case StorageContentType.IMPORT:
                storage = self.spec.defaults.storage.imports or self.default_node().get_storage(
                    content_type=StorageContentType.IMPORT,
                )
            case _:
                storage = ""
        return storage

    @classmethod
    def create(cls, cluster: ClusterStatus | None, mtu: int, reserved_tags: list[int]) -> Self:
        """Create a new ClusterManifest instance with the provided cluster status, MTU, and reserved tags."""
        zone_tag = next(i for i in range(constants.NetworkSettings.BACKPLANE.ZONE_TAG, 100) if i not in reserved_tags)
        vnet_tag = next(i for i in range(constants.NetworkSettings.BACKPLANE.VNET_TAG, 1000) if i not in reserved_tags)
        manifest = cls.model_validate(
            {
                "name": cluster.name if cluster else "OrbitLab",
                "metadata": {
                    "mode": ClusterMode.CLUSTER if cluster else ClusterMode.LOCAL,
                    "version": cluster.version if cluster else 0,
                    "quorate": cluster.quorate if cluster else False,
                    "mtu": mtu,
                },
                "spec": {
                    "backplane": {
                        "zone_id": constants.NetworkSettings.BACKPLANE.NAME,
                        "vnet_id": constants.NetworkSettings.BACKPLANE.NAME,
                        "zone_tag": zone_tag,
                        "vnet_tag": vnet_tag,
                        "mtu": mtu - 50,
                        "cidr_block": constants.NetworkSettings.BACKPLANE.DEFAULT_CIDR,
                        "gateway": constants.NetworkSettings.BACKPLANE.DEFAULT_GATEWAY,
                        "controller": {
                            "id": constants.NetworkSettings.BACKPLANE.NAME,
                            "asn": constants.NetworkSettings.BACKPLANE.ASN,
                        },
                    },
                },
            },
        )
        manifest.save()
        return manifest
