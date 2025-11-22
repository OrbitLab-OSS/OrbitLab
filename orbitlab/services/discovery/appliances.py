"""Appliance Discovery Service."""

from orbitlab.clients.proxmox.exceptions import ApplianceNotFoundError
from orbitlab.data_types import ManifestKind, StorageContentType
from orbitlab.services.discovery.base import DiscoveryService


class ApplianceDiscovery(DiscoveryService):
    """Service for discovering nodes in a Proxmox cluster."""

    def __init__(self) -> None:
        """Initialize the Node discovery service."""
        super().__init__(kind=ManifestKind.BASE_APPLIANCE)
        self.existing = self.manifests.get_existing_by_kind(self._kind)

    async def run(self, *, update: bool = False) -> None:
        for name in self.manifests.get_existing_by_kind(kind=ManifestKind.NODE):
            node_manifest = self.manifests.load(name=name, kind=ManifestKind.NODE)
            for storage in node_manifest.spec.storage.root:
                for content in self.proxmox.list_content_for_storage(node=name, storage=storage.name, content_type=StorageContentType.VZTMPL).root:
                    if content.id in self.existing and not update:
                        continue
                    try:
                        appliance = self.proxmox.describe_appliance(node=name, appliance_id=content.id)
                    except ApplianceNotFoundError:
                        continue
                    manifest = appliance.create_manifest(node=name, storage=storage.name)
                    self.manifests.save(manifest=manifest)
            self.existing = self.manifests.get_existing_by_kind(self._kind)
