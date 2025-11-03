"""Schema definitions for Proxmox cluster node manifests in OrbitLab."""

from typing import Annotated

from pydantic import Field

from orbitlab.clients.proxmox.models import ProxmoxStorage
from orbitlab.data_types import ManifestKind, NodeStatus
from orbitlab.manifest.schemas.networks import BridgeNetworks

from .base import BaseManifest, Metadata, Ref, Spec
from .sdns import SDNManifest
from .serialization import SerializeEnum


class NodeMetadata(Metadata):
    """Metadata for a Proxmox cluster node.

    Attributes:
        hostname (str): The hostname of the node.
        address (str): The network address of the node.
        status (NodeStatus): The current status of the node.
    """
    hostname: str
    status: Annotated[NodeStatus, SerializeEnum]
    maintenance_mode: bool


class NodeSpec(Spec):
    """Specification for a Proxmox cluster node, including its network configurations."""
    bridges: Annotated[list[BridgeNetworks], Field(default_factory=list)]
    sdns: Annotated[list[Ref | SDNManifest], Field(default_factory=list)]
    storage: Annotated[list[ProxmoxStorage], Field(default_factory=list)]


class NodeManifest(BaseManifest[NodeMetadata, NodeSpec]):
    """OrbitLab manifest representing a Proxmox cluster node."""
    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.NODE
