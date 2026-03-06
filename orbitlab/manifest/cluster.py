"""OrbitLab Cluster Manifest Schema."""

import random
from ipaddress import IPv4Address, IPv4Interface, IPv4Network
from typing import TYPE_CHECKING, Annotated, Self, overload

from pydantic import BaseModel, Field

from orbitlab import constants
from orbitlab.data_types import ClusterMode, ManifestKind, OrbitLabApplianceType, StorageContentType, StorageProfile
from orbitlab.services import SecretVault

from .base import BaseManifest, Metadata, Spec
from .nodes import NodeManifest
from .serialization import SerializeEnum, SerializeIP, SerializeIPList

if TYPE_CHECKING:
    from orbitlab.proxmox.base.models import ClusterStatus


class InfraAppliance(BaseModel):
    """OrbitLab Infrastructure Appliance."""

    node: str
    volume_id: str


class ClusterMetadata(Metadata):
    """Metadata for cluster manifest containing cluster-specific configuration."""

    initialized: bool = False
    mode: Annotated[ClusterMode, SerializeEnum]
    version: int
    quorate: bool
    mtu: int
    reserved_tags: list[int] = Field(default_factory=list)
    infrastructure_version: str = ""
    infrastructure_appliances: dict[OrbitLabApplianceType, InfraAppliance] = Field(default_factory=dict)


class Controller(BaseModel):
    """Controller configuration for cluster networking."""

    id: str
    asn: int
    peers: Annotated[list[IPv4Address], SerializeIPList] = Field(default_factory=list)

    @property
    def peer_list(self) -> str:
        """Return a comma-separated string of peer IP addresses."""
        return ",".join([str(peer) for peer in self.peers])


class IPAssignment(BaseModel):
    """An IP address assignment to a virtual machine or LXC."""

    address: Annotated[IPv4Address, SerializeIP]
    description: str
    is_vip: bool = False


class Backplane(BaseModel):
    """Represents the backplane network configuration for the cluster."""

    zone_id: str
    vnet_id: str
    controller: Controller
    zone_tag: int
    vnet_tag: int
    mtu: int
    cidr_block: Annotated[IPv4Network, SerializeIP]
    dns_vmid: int = 0
    assignments: list[IPAssignment] = Field(default_factory=list)

    @property
    def gateway_address(self) -> IPv4Interface:
        """Get the Default Gateway IP address for the backplane."""
        return IPv4Interface(f"{self.cidr_block.network_address + 1}/{self.cidr_block.prefixlen}")

    @property
    def dns_address(self) -> IPv4Interface:
        """Get the DNS IP address for the backplane."""
        return IPv4Interface(f"{self.cidr_block.network_address + 2}/{self.cidr_block.prefixlen}")


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


class ETCDMember(BaseModel):
    """Represents an ETCD cluster member."""

    vmid: int
    name: str
    address: Annotated[IPv4Interface, SerializeIP]


class ETCD(BaseModel):
    """ETCD cluster configuration."""

    members: list[ETCDMember]

    def create_member(self, vmid: int, name: str, address: IPv4Interface) -> ETCDMember:
        """Create a new ETCD cluster member."""
        return ETCDMember(vmid=vmid, name=name, address=address)

    def get_member(self, member_name: str) -> ETCDMember | None:
        """Get an ETCD member by name."""
        return next(iter(member for member in self.members if member.name == member_name), None)

    def get_active_member(self, *, failing_member: str = "") -> ETCDMember:
        """Get an random active ETCD member by excluding the failing member."""
        return random.choice([member for member in self.members if member.name != failing_member])  # noqa: S311


class ClusterSpec(Spec):
    """Specification for an OrbitLab cluster."""

    nodes: list[str] = Field(default_factory=list)
    backplane: Backplane
    defaults: Defaults = Defaults()
    used_vlan_tags: list[int] = Field(default_factory=list)
    etcd: ETCD | None = None


class ClusterManifest(BaseManifest[ClusterMetadata, ClusterSpec]):
    """Manifest schema for an OrbitLab cluster."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.CLUSTER

    @property
    def exit_nodes(self) -> str:
        """Return a comma-separated string of all cluster node names."""
        return ",".join(self.spec.nodes)

    def assign_ip(self, address: IPv4Address, description: str, *, is_vip: bool = False) -> None:
        """Add an IP assignment."""
        self.spec.backplane.assignments.append(IPAssignment(address=address, description=description, is_vip=is_vip))
        self.save()

    def release_ip(self, address: IPv4Address) -> None:
        """Release the IP address assigned to the given VMID using the backplane IPAM manifest."""
        assignment = next(
            iter([assigned for assigned in self.spec.backplane.assignments if assigned.address == address]),
            None,
        )
        if assignment:
            self.spec.backplane.assignments.remove(assignment)
            self.save()

    @overload
    def get_next_available_ip(self, *, count: None = None) -> IPv4Interface: ...

    @overload
    def get_next_available_ip(self, *, count: int) -> list[IPv4Interface]: ...

    def get_next_available_ip(self, *, count: int | None = None) -> IPv4Interface | list[IPv4Interface]:
        """Get the next available IP address in the subnet."""
        assigned = [assigned.address for assigned in self.spec.backplane.assignments]
        hosts = list(self.spec.backplane.cidr_block.hosts())
        usable = hosts[constants.NetworkSettings.RESERVED_INFRA_IPS:constants.NetworkSettings.RESERVED_BROADCAST_IPS]
        if count:
            available = iter(
                IPv4Interface(f"{ip}/{self.spec.backplane.cidr_block.prefixlen}") for ip in usable if ip not in assigned
            )
            return [next(available) for _ in range(count)]
        return next(iter(
            IPv4Interface(f"{ip}/{self.spec.backplane.cidr_block.prefixlen}") for ip in usable if ip not in assigned
        ))

    def get_default_storage(self, content_type: StorageContentType) -> str:
        match content_type:
            case StorageContentType.IMAGES:
                return self.spec.defaults.storage.images
            case StorageContentType.IMPORT:
                return self.spec.defaults.storage.imports
            case StorageContentType.VZTMPL:
                return self.spec.defaults.storage.vztmpl
            case StorageContentType.ROOTDIR:
                return self.spec.defaults.storage.rootdir

    def add_node(self, node: NodeManifest) -> None:
        """Add a node to the cluster and update the backplane controller peers."""
        self.spec.nodes.append(node.name)
        self.spec.backplane.controller.peers.append(node.metadata.ip)
        self.save()

    def get_nodes(self) -> list[NodeManifest]:
        """Return a list of all NodeManifest objects for nodes in this cluster."""
        return [NodeManifest.load(name=node) for node in self.spec.nodes]

    def default_node(self) -> NodeManifest:
        """Get the default node for the cluster."""
        return NodeManifest.load(name=self.spec.defaults.node)

    def set_tag_as_unused(self, tag: int) -> None:
        """Remove a specified VLAN tag so it may be used again."""
        if tag in self.spec.used_vlan_tags:
            self.spec.used_vlan_tags.remove(tag)
            self.save()

    def get_next_available_tag(self, start: int = 1000, end: int = 9999) -> int:
        """Find the next available network tag in the range 1000-9999."""
        existing_tags = set(list(self.spec.used_vlan_tags) + self.metadata.reserved_tags)
        try:
            tag = next(i for i in range(start, end + 1) if i not in existing_tags)
            self.spec.used_vlan_tags.append(tag)
            self.save()
        except StopIteration as e:
            msg = f"There are no available tags between {start} and {end}."
            raise ValueError(msg) from e
        else:
            return tag

    @classmethod
    def create(cls, cluster: "ClusterStatus | None", mtu: int, reserved_tags: list[int]) -> Self:
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

    @classmethod
    def generate_empty_etcd(cls) -> ETCD:
        """Generate an empty ETCD configuration."""
        return ETCD(members=[])

    @classmethod
    def generate_etcd_member_name(cls) -> str:
        """Generate a unique ETCD member name."""
        return cls._generate_id(prefix="etcd", count=6, skip_check=True)

    def generate_etcd_member_create_params(self, vmid: int, name: str, address: IPv4Interface) -> dict:
        """Generate parameters for creating an ETCD member LXC container."""
        return {
            "features": "nesting=1",
            "ostemplate": self.metadata.etcd_appliance.volume_id,
            "hostname": name,
            "cores": 2,
            "memory": 1024,
            "swap": 1024,
            "net0": (
                f"name=eth0,bridge={self.spec.backplane.vnet_id},ip={address},gw={self.spec.backplane.gateway_address.ip}"
            ),
            "rootfs": f"{self.spec.defaults.storage.rootdir}:8",
            "unprivileged": "1",
            "vmid": vmid,
            "ssh-public-keys": "",
            "password": SecretVault.generate_random_password(),
            "searchdomain": "orbitlab.internal",
            "nameserver": f"{self.spec.backplane.dns_address.ip}",
            "onboot": "1",
        }
