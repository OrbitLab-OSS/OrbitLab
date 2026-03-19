"""OrbitLab Defaults."""

import reflex as rx

from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.sector import SectorManifest
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

    @rx.var
    def images_storage(self) -> str:
        """Get the default images (VM Disks) storage name from the cluster manifest, or an empty string if not set."""
        if self._cluster:
            return self._cluster.spec.defaults.storage.images
        return ""

    @rx.var
    def rootdir_storage(self) -> str:
        """Get the default rootdir storage name from the cluster manifest, or an empty string if not set."""
        if self._cluster:
            return self._cluster.spec.defaults.storage.rootdir
        return ""

    @rx.var
    def vztmpl_storage(self) -> str:
        """Get the default vztmpl storage name from the cluster manifest, or an empty string if not set."""
        if self._cluster:
            return self._cluster.spec.defaults.storage.vztmpl
        return ""

    @rx.var(cache=False)
    def available_nodes(self) -> list[str]:
        """Get the list of available Proxmox nodes from the cluster manifest, or an empty list if not set."""
        if self._cluster:
            return list(self._cluster.spec.nodes.keys())
        return []

    @rx.var(cache=False)
    def available_sectors(self) -> dict[str, str]:
        """Get the available sectors as a dictionary mapping display names to sector names."""
        return {
            f"{sector.spec.alias} ({sector.spec.cidr_block})": sector.name
            for sector in [SectorManifest.load(name=name) for name in SectorManifest.get_existing()]
        }

    @rx.var
    def etcd_enabled(self) -> bool:
        if self._cluster:
            return bool(self._cluster.spec.etcd)
        return False
