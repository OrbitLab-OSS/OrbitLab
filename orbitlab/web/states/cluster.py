"""State management for Proxmox nodes."""

import reflex as rx

from orbitlab.data_types import ManifestKind
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.cluster import ClusterManifest
from orbitlab.manifest.schemas.nodes import NodeManifest
from orbitlab.manifest.schemas.settings import OrbitLabSettingsManifest


def get_node_manifests() -> list[NodeManifest]:
    manifest_client = ManifestClient()
    existing = manifest_client.get_existing_by_kind(kind=ManifestKind.NODE)
    if not existing:
        return []
    existing = manifest_client.get_existing_by_kind(kind=ManifestKind.NODE)
    nodes = [manifest_client.load(node, kind=ManifestKind.NODE) for node in existing]
    return sorted(nodes, key=lambda node: node.name)


class ProxmoxNodesState(rx.State):
    """State management for Proxmox nodes."""

    refresh_nodes: bool = False
    refresh_rate: int = 10
    nodes: list[NodeManifest] = rx.field(default_factory=get_node_manifests)


def get_cluster_manifest() -> ClusterManifest | None:
    existing = ManifestClient().get_existing_by_kind(kind=ManifestKind.CLUSTER)
    if not existing:
        return None
    manifest_name = next(iter(existing.keys()))
    return ManifestClient().load(name=manifest_name, kind=ManifestKind.CLUSTER)


class ProxmoxClusterState(rx.State):
    cluster: ClusterManifest | None = rx.field(default_factory=get_cluster_manifest)


class OrbitLabSettings(rx.State):
    @rx.var
    def _settings(self) -> OrbitLabSettingsManifest | None:
        manifest_client = ManifestClient()
        name = next(iter(manifest_client.get_existing_by_kind(kind=ManifestKind.SETTINGS).keys()), None)
        if name:
            return manifest_client.load(name=name, kind=ManifestKind.SETTINGS)
        return None

    @rx.var
    def primary_node(self) -> str:
        if self._settings:
            return self._settings.metadata.primary_node
        return ""

    @rx.var
    def default_vztmpl_storage(self) -> str:
        if self._settings:
            return self._settings.spec.default_storage_selections.vztmpl or ""
        return ""
