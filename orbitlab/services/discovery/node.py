"""Nodes Discovery Service."""

from orbitlab.clients.proxmox.models import ProxmoxApplianceInfo, ProxmoxNetwork, ProxmoxNode, ProxmoxStorage
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

    def run(self) -> None:
        """Run the node discovery process."""
        # for apl in self.proxmox.get("/nodes/pve-1-1/aplinfo", model=ProxmoxApplianceInfo):
        #     if "centos" in apl.headline.lower():
        #         self.proxmox.download_lxc("pve-1-1", "cloudinit", apl)
        print(self.proxmox.get_task_status(node="pve-1-1", upid="UPID:pve-1-1:00081B21:068C5B90:68F5378D:download:centos-9-stream-default_20240828_amd64.tar.xz:root@pam:"))

    def __discover_nodes__(self, *, update: bool = False) -> None:
        """Discover and save manifests for all online nodes in the Proxmox cluster."""
        nodes = self.proxmox.get("/nodes", model=ProxmoxNode)
        for node in nodes:
            if node.name in self.existing and not update:
                continue
            if node.status != NodeStatus.ONLINE:
                # Can't discover a node that's not online
                continue
            bridges = self.proxmox.get(f"/nodes/{node.name}/network", model=ProxmoxNetwork)
            storage = self.proxmox.get(f"/nodes/{node.name}/storage", model=ProxmoxStorage)
            sdns = self.sdn_discovery.get_sdns_for_node(node)
            manifest = NodeManifest(
                name=node.name,
                metadata=NodeMetadata(
                    hostname=node.name,
                    status=node.status,
                ),
                spec=NodeSpec(
                    bridges=[bridge.model_dump() for bridge in bridges if bridge.cidr],
                    sdns=sdns,
                    storage=storage,
                ),
            )
            self.manifests.save(manifest)
