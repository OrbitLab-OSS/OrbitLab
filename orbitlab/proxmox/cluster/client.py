"""Proxmox Cluster Client."""

from orbitlab.proxmox.base import Proxmox
from orbitlab.proxmox.base.models import ProxmoxClusterStatus

from .models import CurrentHAStatus, StorageResources


class ProxmoxCluster(Proxmox):
    """Proxmox cluster management client."""

    async def get_status(self) -> ProxmoxClusterStatus:
        """Get the status of the Proxmox cluster."""
        return await self.get(path="/cluster/status", model=ProxmoxClusterStatus)

    async def get_ha_status(self) -> CurrentHAStatus:
        """Get the current High Availability status from the Proxmox cluster."""
        return await self.get(path="/cluster/ha/status/current", model=CurrentHAStatus)

    async def list_storage_resources(self) -> StorageResources:
        """List all storage resources in the Proxmox cluster."""
        params = {"type": "storage"}
        return await self.get(path="/cluster/resources", model=StorageResources, **params)

    async def node_online(self, name: str) -> bool:
        status = await self.get_status()
        node = status.get_node(name=name)
        return node.online

    async def node_maintenance_mode(self, name: str) -> bool:
        status = await self.get_ha_status()
        return status.in_maintenance_mode(node=name)
