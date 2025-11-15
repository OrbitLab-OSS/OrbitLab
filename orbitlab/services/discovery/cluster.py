from orbitlab.clients.proxmox.models import ClusterStatus
from orbitlab.data_types import ManifestKind
from orbitlab.manifest.schemas.cluster import ClusterManifest, ClusterMetadata, ClusterSpec
from orbitlab.services.discovery.base import DiscoveryService


class Cluster(DiscoveryService):
    def __init__(self) -> None:
        super().__init__(kind=ManifestKind.CLUSTER)
        self.existing = self.manifests.get_existing_by_kind(self._kind)

    async def run(self, *, update: bool = False) -> str:
        cluster_items = self.proxmox.get_cluster_status()
        try:
            cluster = next(iter(item for item in cluster_items.root if isinstance(item, ClusterStatus)))
        except StopIteration:
            return None
        if cluster.name in self.existing and not update:
            return cluster.name
        manifest = ClusterManifest(
            name=cluster.name,
            metadata=ClusterMetadata(
                name=cluster.name,
                version=cluster.version,
                node_count=cluster.nodes,
            ),
            spec=ClusterSpec(quorate=cluster.quorate),
        )
        self.manifests.save(manifest=manifest)
        return cluster.name
