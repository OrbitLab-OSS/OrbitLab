"""Networks Discovery Service."""

from orbitlab.clients.proxmox.client import Proxmox
from orbitlab.clients.proxmox.models import ProxmoxNode, ProxmoxSDNSubnet, ProxmoxSDNZone
from orbitlab.data_types import ManifestKind
from orbitlab.manifest.schemas.sdns import SDNManifest
from orbitlab.services.discovery.base import DiscoveryService


class SDN(DiscoveryService):
    """Service for discovering Software Defined Networks in a Proxmox cluster."""
    def __init__(self, proxmox: Proxmox | None = None) -> None:
        """Initialize the SDN discovery service."""
        super().__init__(kind=ManifestKind.SDN, proxmox=proxmox)
        self.existing = self.manifests.get_existing_by_kind(self._kind)

    def run(self) -> None:
        """Run the SDN discovery process."""
        self.__discover_sdns__()

    def get_sdns_for_node(self, node: ProxmoxNode) -> list[SDNManifest]:
        """Retrieve SDN manifests for a given Proxmox node.

        Args:
            node (ProxmoxNode): The Proxmox node to retrieve SDN manifests for.

        Returns:
            list[SDNManifest]: A list of SDNManifest objects associated with the node.
        """
        items = self.proxmox.get(f"/nodes/{node.name}/sdn/zones")
        manifests = []
        for item in items:
            zone_name = item["zone"]
            if zone_name in self.existing:
                manifests.append(
                    self.manifests.load(zone_name, self._kind, SDNManifest),
                )
        return manifests

    def __discover_sdns__(self) -> None:
        """Discover SDN zones and their subnets in the Proxmox cluster."""
        zones = self.proxmox.get("/cluster/sdn/zones", model=ProxmoxSDNZone)
        for zone in zones:
            if zone.zone_name in self.existing:
                continue
            subnets = self.proxmox.get(f"/cluster/sdn/vnets/{zone.zone_name}/subnets", model=ProxmoxSDNSubnet)
            if not subnets:
                continue
            data = {
                "name": zone.zone_name,
                "metadata": {
                    "zone_type": zone.zone_type,
                    "zone_name": zone.zone_name,
                    "mac": zone.mac,
                    "controller": zone.controller,
                },
                "spec": {
                    "mtu": zone.mtu,
                    "subnets": [
                        {
                            "dns_prefix": subnet.dns_prefix,
                            "gateway": subnet.gateway,
                            "cidr_block": subnet.cidr_block,
                            "dhcp_ranges": [
                                {
                                    "start": dhcp.start,
                                    "end": dhcp.end,
                                } for dhcp in subnet.dhcp_ranges
                            ],
                        } for subnet in subnets
                    ],
                },
            }
            self.manifests.save(SDNManifest.model_validate(data))
