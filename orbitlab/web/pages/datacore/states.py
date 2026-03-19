"""DataCore States."""

import reflex as rx

from orbitlab.data_types import ETCDStatus, StorageContentType
from orbitlab.manifest.datacore import DataCoreManifest
from orbitlab.proxmox import Proxmox
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.utilities import CacheBuster, get_redis_value


class DataCoreServiceState(CacheBuster, rx.State):
    """State for DataCore service management."""

    confirm_delete_etcd: rx.Field[str] = rx.field(default="")

    @rx.var(deps=["_cached_etcd_cluster_status"])
    async def etcd_cluster_status(self) -> ETCDStatus:
        return ETCDStatus(await get_redis_value(name="ol:datacore:etcd:cluster", key="status", default=ETCDStatus.ABSENT.value))

    @rx.var
    async def etcd_mutation_in_progress(self) -> bool:
        return await self.etcd_cluster_status in (ETCDStatus.PENDING, ETCDStatus.DELETING)

    @rx.var(deps=["_cached_clusters"])
    def clusters(self) -> list[DataCoreManifest]:
        """Return a list of DataCore cluster manifests."""
        return [DataCoreManifest.load(name=name) for name in DataCoreManifest.get_existing()]

    @rx.var
    async def state_map(self) -> dict[str, str]:
        """Return a mapping of DataCore cluster names to their current states."""
        return {
            manifest.name: await get_redis_value(name=f"ol:datacore:{manifest.name}", key="state", default="pending")
            for manifest in self.clusters
        }


class CreateDataCoreDialogState(rx.State):
    """State for DataCore Creation Dialog."""

    replicas: rx.Field[int] = rx.field(default=1)
    memory_gb: rx.Field[int] = rx.field(default=2)
    cores: rx.Field[int] = rx.field(default=2)
    capacity_gb: rx.Field[int] = rx.field(default=100)
    view_app_password: rx.Field[bool] = rx.field(default=False)

    @rx.var
    async def node(self) -> str:
        """Return the configured Proxmox node."""
        return await self.get_var_value(ClusterDefaults.proxmox_node)

    @rx.var
    async def rootdir_storage(self) -> str:
        """Return the default configured storage for LXC rootdirs."""
        return await self.get_var_value(ClusterDefaults.rootdir_storage)

    @rx.var
    async def available_rootdir_storages(self) -> list[str]:
        """Return a list of available rootdir storages for the configured node."""
        node = await self.node
        if node:
            return Proxmox().list_storages_for_node(node=node, content_type=StorageContentType.ROOTDIR)
        return []


class DeleteDataCoreDialogState(rx.State):
    """State for DataCore Deletion Dialog."""

    name: str = ""
    confirmation: str = ""

    @rx.var
    def delete_disabled(self) -> bool:
        """Return True if the delete action should be disabled (name and confirmation do not match)."""
        return self.name != self.confirmation
