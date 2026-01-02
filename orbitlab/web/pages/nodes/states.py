"""OrbitLab Proxmox Nodes States."""

import reflex as rx

from orbitlab.manifest.nodes import NodeManifest
from orbitlab.web.utilities import CacheBuster


class ProxmoxState(CacheBuster, rx.State):
    """State class for managing Proxmox node manifests and related utilities."""

    @rx.var
    def nodes(self) -> list[NodeManifest]:
        """Get all existing node manifests."""
        return [NodeManifest.load(name=name) for name in NodeManifest.get_existing()]

    @rx.var
    def node_names(self) -> list[str]:
        """Get a list of node names from all node manifests."""
        return [node.name for node in self.nodes]
