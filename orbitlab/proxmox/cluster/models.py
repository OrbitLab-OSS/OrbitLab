"""Proxmox Cluster Client Models."""

from pydantic import BaseModel, RootModel

from orbitlab.manifest.serialization import PveBool, PveContentList


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
