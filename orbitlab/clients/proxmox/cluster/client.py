"""Proxmox Cluster Client."""

from orbitlab.clients.proxmox.base import Proxmox

from .models import CurrentHAStatus, ProxmoxClusterStatus, StorageResources


class ProxmoxCluster(Proxmox):
    """Proxmox cluster management client."""

    def get_status(self) -> ProxmoxClusterStatus:
        """Get the status of the Proxmox cluster."""
        return self.get(path="/cluster/status", model=ProxmoxClusterStatus)

    def get_ha_status(self) -> CurrentHAStatus:
        """Get the current High Availability status from the Proxmox cluster."""
        return self.get(path="/cluster/ha/status/current", model=CurrentHAStatus)

    def list_storage_resources(self) -> StorageResources:
        """List all storage resources in the Proxmox cluster."""
        params = {"type": "storage"}
        return self.get(path="/cluster/resources", model=StorageResources, **params)
