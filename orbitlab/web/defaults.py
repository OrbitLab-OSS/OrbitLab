"""OrbitLab Defaults."""

import reflex as rx

from orbitlab.manifest.cluster import ClusterManifest


class ClusterDefaults(rx.State):
    """State management for cluster default settings."""

    @rx.var
    def proxmox_node(self) -> str:
        """Get the default Proxmox node name from the cluster manifest, or an empty string if not set."""
        name = next(iter(ClusterManifest.get_existing()), "")
        if name:
            cluster = ClusterManifest.load(name=name)
            return cluster.spec.defaults.node
        return ""
