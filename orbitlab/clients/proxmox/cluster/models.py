"""Proxmox Cluster Client Models."""

import ipaddress
from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel

from orbitlab.manifest.serialization import PveBool, PveContentList


class NodeStatus(BaseModel):
    """Represents the status of a Proxmox cluster node."""

    node_id: Annotated[int, Field(alias="nodeid")]
    local: PveBool
    online: PveBool
    type: Literal["node"]
    ip: ipaddress.IPv4Address | None = None
    name: str
    maintenance_mode: bool = False


class ClusterStatus(BaseModel):
    """Represents the status of a Proxmox cluster."""

    name: str
    quorate: PveBool
    type: Literal["cluster"]
    quorate: bool
    version: int
    nodes: int


class ProxmoxClusterStatus(RootModel[list[Annotated[ClusterStatus | NodeStatus, Field(discriminator="type")]]]):
    """Represents the status of a Proxmox cluster including nodes and cluster information."""

    def get_nodes(self) -> list[NodeStatus]:
        """Get all nodes from the cluster status."""
        return [item for item in self.root if isinstance(item, NodeStatus)]

    def get_local_node(self) -> str:
        """Get the name of the local node from the cluster status."""
        return next(iter(node.name for node in self.get_nodes() if node.local))

    def get_cluster(self) -> ClusterStatus | None:
        """Get the cluster status from the cluster status list."""
        return next(iter(item for item in self.root if isinstance(item, ClusterStatus)), None)


class HANode(BaseModel):
    """Represents a High Availability node in a Proxmox cluster."""

    id: str
    node: str
    quorate: PveBool
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

    content: PveContentList
    id: str
    node: str
    plugintype: str
    shared: PveBool
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
