"""Schema definitions for Proxmox cluster node manifests in OrbitLab."""

from ipaddress import IPv4Address
from typing import Annotated

from pydantic import BaseModel, Field

from orbitlab.data_types import ManifestKind, StorageContentType

from .base import BaseManifest, Metadata, Spec
from .serialization import SerializeEnum, SerializeEnumList, SerializeIP


class NodeMetadata(Metadata):
    """Metadata for a Proxmox cluster node.

    Attributes:
        address (str): The network address of the node.
        status (NodeStatus): The current status of the node.
    """

    ip: Annotated[IPv4Address, SerializeIP]
    online: bool
    maintenance_mode: bool


class Storage(BaseModel):
    """Storage configuration for a Proxmox node."""

    name: str
    content: Annotated[list[StorageContentType], SerializeEnumList]
    shared: bool


class NodeSpec(Spec):
    """Specification for a Proxmox cluster node, including its network configurations."""

    storage: list[Storage] = Field(default_factory=list)


class NodeManifest(BaseManifest[NodeMetadata, NodeSpec]):
    """OrbitLab manifest representing a Proxmox cluster node."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.NODE
