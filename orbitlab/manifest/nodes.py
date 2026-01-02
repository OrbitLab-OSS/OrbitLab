"""Schema definitions for Proxmox cluster node manifests in OrbitLab."""

from ipaddress import IPv4Address
from typing import Annotated

from pydantic import BaseModel, Field

from orbitlab.clients.proxmox.cluster.models import NodeStatus
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
    networking_configured: bool = False


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

    def list_storages(self, content_type: StorageContentType) -> list[str]:
        """List storage names that support the specified content type."""
        return [storage.name for storage in self.spec.storage if content_type in storage.content]

    def get_storage(self, content_type: StorageContentType) -> str:
        """Get the first storage name that supports the specified content type."""
        return next(iter(self.list_storages(content_type=content_type)))

    @classmethod
    def from_node_status(cls, node: NodeStatus, storage: list[dict]) -> "NodeManifest":
        """Create a NodeManifest instance from a NodeStatus object and storage list."""
        manifest = cls.model_validate(
            {
                "name": node.name,
                "metadata": {
                    "ip": node.ip,
                    "online": node.online,
                    "maintenance_mode": node.maintenance_mode,
                },
                "spec": {
                    "storage": storage,
                },
            },
        )
        manifest.save()
        return manifest
