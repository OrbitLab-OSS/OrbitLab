"""DockFS States."""

import reflex as rx

from orbitlab.data_types import StorageContentType
from orbitlab.manifest.dockfs import DockFsManifest
from orbitlab.proxmox import Proxmox
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.utilities import CacheBuster, get_redis_value


class DockFSTableState(CacheBuster, rx.State):
    """State for DockFS Management Table."""

    @rx.var(deps=["_cached_clusters"])
    def clusters(self) -> list[DockFsManifest]:
        """Return a list of DockFS cluster manifests."""
        return [DockFsManifest.load(name=name) for name in DockFsManifest.get_existing()]

    @rx.var
    async def state_map(self) -> dict[str, str]:
        """Return a mapping of VM manifest names to their states."""
        return {
            manifest.name: await get_redis_value(name=f"ol:dockfs:{manifest.name}", key="state", default="pending")
            for manifest in self.clusters
        }


class CreateDockFSDialogState(rx.State):
    """State for DockFS Creation Dialog."""

    memory_gb: rx.Field[int] = rx.field(default=2)
    cores: rx.Field[int] = rx.field(default=2)
    sockets: rx.Field[int] = rx.field(default=1)
    capacity_gb: rx.Field[int] = rx.field(default=100)

    @rx.var
    async def node(self) -> str:
        """Return the configured Proxmox node."""
        return await self.get_var_value(ClusterDefaults.proxmox_node)

    @rx.var
    async def disk_storage(self) -> str:
        """Return the configured disk storage for images."""
        return await self.get_var_value(ClusterDefaults.images_storage)

    @rx.var
    async def available_disk_storages(self) -> list[str]:
        """Return a list of available disk storages for the configured node."""
        node = await self.node
        if node:
            return Proxmox().list_storages_for_node(node=node, content_type=StorageContentType.IMAGES)
        return []


class DeleteDockFSDialogState(rx.State):

    name: str = ""
    confirmation: str = ""

    @rx.var
    def delete_disabled(self) -> bool:
        """Return True if the delete action should be disabled (name and confirmation do not match)."""
        return self.name != self.confirmation
