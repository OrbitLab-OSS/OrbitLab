"""OrbitLab Defaults."""

import reflex as rx

from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.web.utilities import CacheBuster


class ClusterDefaults(CacheBuster, rx.State):
    """State management for cluster default settings."""

    @rx.var(deps=["_cached__cluster"])
    def _cluster(self) -> ClusterManifest | None:
        name = next(iter(ClusterManifest.get_existing()), "")
        if name:
            return ClusterManifest.load(name=name)
        return None

    @rx.var
    def proxmox_node(self) -> str:
        """Get the default Proxmox node name from the cluster manifest, or an empty string if not set."""
        if self._cluster:
            return self._cluster.spec.defaults.node
        return ""

    @rx.var
    def import_storage(self) -> str:
        """Get the default import storage name from the cluster manifest, or an empty string if not set."""
        if self._cluster:
            return self._cluster.spec.defaults.storage.imports
        return ""
