"""Discovery Service base."""

from orbitlab.data_types import SectorState
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.compute_templates.appliances import BaseApplianceManifest
from orbitlab.manifest.nodes import NodeManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.proxmox import ProxmoxCluster, ProxmoxNetworks
from orbitlab.proxmox.compute_templates import ProxmoxComputeTemplates


class DiscoveryService:
    """Service for discovering and managing Proxmox resources."""

    def __init__(self) -> None:
        """Initialize the Discovery Service."""
        self.cluster = ProxmoxCluster()
        self.networks = ProxmoxNetworks()
        self.appliances = ProxmoxComputeTemplates()

    def discover_cluster(self) -> ClusterManifest | None:
        """Discover and return cluster configuration."""
        if existing := ClusterManifest.get_existing():
            return ClusterManifest.load(name=next(iter(existing)))

        invalid_node_count = 2
        status = self.cluster.get_status()
        if len(status.get_nodes()) == invalid_node_count:
            return None

        cluster_manifest = ClusterManifest.create(
            cluster=status.get_cluster(),
            mtu=self.networks.get_mtu(),
            reserved_tags=self.networks.list_vnets().get_all_tags(),
        )
        return cluster_manifest

    def discover_nodes(self, manifest: ClusterManifest) -> None:
        ha_status = self.cluster.get_ha_status()
        storage_resources = self.cluster.list_storage_resources()
        for node in self.cluster.get_status().get_nodes():
            node.maintenance_mode = ha_status.in_maintenance_mode(node=node.name)
            node_manifest = NodeManifest.from_node_status(
                node=node,
                storage=storage_resources.get_storage_for_node(node=node.name),
            )
            manifest.add_node(node=node_manifest)
        manifest.save()

    def discover_sectors(self, cluster: ClusterManifest) -> None:
        """Run Sector discovery."""
        existing = SectorManifest.get_existing()
        for sector in self.networks.list_sectors():
            if sector.vnet.name in existing:
                continue
            sector_manifest = SectorManifest.model_validate(
                {
                    "name": sector.vnet.name,
                    "metadata": {
                        "alias": sector.vnet.alias,
                        "tag": sector.vnet.tag,
                        "state": SectorState.AVAILABLE,
                    },
                    "spec": {
                        "cidr_block": sector.subnets.get_cidr(),
                        "subnets": [
                            {
                                "cidr_block": subnet.cidr,
                                "name": f"subnet-{index}",
                            }
                            for index, subnet in enumerate(sector.subnets.root)
                        ],
                        "gateway_vmid": sector.gateway_vmid,
                    },
                },
            )
            sector_manifest.save()
            # cluster.add_sector(tag=sector.vnet.tag, ref=sector_manifest.to_ref())
            # for vmid, address in sector.assignments.items():
            #     if subnet := ipam.get_subnet_by_ip(address=address):
            #         subnet.add_assignment(vmid=vmid, address=address)
            # ipam.save()

    def discover_appliances(self) -> None:
        """Discover and create manifests for stored appliances in the cluster."""
        cluster = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        existing_appliances = BaseApplianceManifest.get_existing()
        # for node in cluster.get_nodes():
        #     for storage in node.spec.storage:
        #         for appliance in self.appliances.list_stored_appliances(node=node.name, storage=storage.name):
                    # manifest = BaseApplianceManifest.create_from_stored_appliance(
                    #     node_ref=node.to_ref(),
                    #     appliance=appliance,
                    # )
                    # if manifest.name not in existing_appliances:
                    #     manifest.save()
