"""Nodes Discovery Service."""

from orbitlab.clients.proxmox.models import ProxmoxNetworks, ProxmoxNodes, ProxmoxStorages
from orbitlab.data_types import ManifestKind, NodeStatus
from orbitlab.manifest.schemas.nodes import NodeManifest, NodeMetadata, NodeSpec
from orbitlab.services.discovery.base import DiscoveryService
from orbitlab.services.discovery.sdn import SDN


class Node(DiscoveryService):
    """Service for discovering nodes in a Proxmox cluster."""

    def __init__(self) -> None:
        """Initialize the Node discovery service."""
        super().__init__(kind=ManifestKind.NODE)
        self.existing = self.manifests.get_existing_by_kind(self._kind)
        self.sdn_discovery = SDN(proxmox=self.proxmox)

    async def run(self, *, update: bool = False) -> None:
        nodes = self.proxmox.get("/nodes", model=ProxmoxNodes)
        for node in nodes.root:
            if node.name in self.existing and not update:
                continue
            if node.status != NodeStatus.ONLINE:
                # Can't discover a node that's not online
                continue
            bridges = self.proxmox.get(f"/nodes/{node.name}/network", model=ProxmoxNetworks).root
            storage = self.proxmox.get(f"/nodes/{node.name}/storage", model=ProxmoxStorages).root
            sdns = self.sdn_discovery.get_sdns_for_node(node)
            manifest = NodeManifest(
                name=node.name,
                metadata=NodeMetadata(
                    hostname=node.name,
                    status=node.status,
                    maintenance_mode=self.proxmox.node_in_maintenance_mode(node=node.name),
                ),
                spec=NodeSpec(
                    bridges=[bridge.model_dump() for bridge in bridges if bridge.cidr],
                    sdns=sdns,
                    storage=storage,
                ),
            )
            self.manifests.save(manifest)
