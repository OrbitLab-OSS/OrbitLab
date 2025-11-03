
"""State management for Proxmox nodes."""

import reflex as rx

from orbitlab.clients.proxmox.client import Proxmox
from orbitlab.clients.proxmox.models import ProxmoxNode
from orbitlab.data_types import ManifestKind, NodeStatus
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.nodes import NodeManifest


class NodeInfo(ProxmoxNode):
    """Extended Proxmox node information including maintenance mode status.

    Attributes:
        maintenance_mode (bool): Whether the node is in maintenance mode.
    """
    maintenance_mode: bool = False


class ProxmoxNodesState(rx.State):
    """State management for Proxmox nodes."""
    refresh_nodes: bool = False
    refresh_rate: int = 10

    @rx.var(interval=5)
    def nodes(self) -> list[NodeInfo]:
        """Get the list of online Proxmox nodes with their maintenance status.

        Returns:
            list[NodeInfo]: A sorted list of NodeInfo objects for nodes that are online and have manifests.
        """
        if self.refresh_nodes:
            self.refresh_nodes = False
        manifest_client = ManifestClient()
        existing = manifest_client.get_existing_by_kind(kind=ManifestKind.NODE)
        nodes = []
        for node in Proxmox().get("/nodes", model=NodeInfo):
            if node.status == NodeStatus.ONLINE and node.name in existing:
                manifest = manifest_client.load(node.name, kind=ManifestKind.NODE, model=NodeManifest)
                node.maintenance_mode = manifest.metadata.maintenance_mode
                nodes.append(node)
        return sorted(nodes, key=lambda node: node.name)
