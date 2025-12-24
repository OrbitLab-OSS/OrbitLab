"""Discovery Service base."""

from orbitlab.clients.proxmox import ProxmoxCluster, ProxmoxNetworks
from orbitlab.clients.proxmox.appliances import ProxmoxAppliances
from orbitlab.manifest.appliances import BaseApplianceManifest
from orbitlab.manifest.cluster import ClusterManifest


class NodeManagement:
    """Manage Proxmox Nodes for OrbitLab purposes."""

    def __init__(self, node: str) -> None:
        """Initialize the node manager."""
        self.node = node

    def configure_networking(self) -> None:
        """Configure required network services on the Proxmox node."""
        remote_node = ProxmoxCluster().create_connection(node=self.node)
        remote_node.run_command("apt update -y")
        remote_node.run_command("apt install -y frr frr-pythontools")
        remote_node.run_command("sed -i 's|bgpd=no|bgpd=yes|' /etc/frr/daemons")
        remote_node.run_command("systemctl enable frr && systemctl restart frr")

    def configure_linstor(self) -> None:
        """Configure Linstor DRBD on the Proxmox Node.

        Linstor is favored over Ceph for a few reasons. The primary reason is that is has better performance
        over Ceph when using it for 'home-lab' purposes and can work better on lower-throughput networks. Ceph
        really should be used when the network is >=10GbE, which isn't common for most end-user home labs.
        """
        raise NotImplementedError
        # # apt install proxmox-headers-$(uname -r)
        # wget -O /tmp/linbit-keyring.deb https://packages.linbit.com/public/linbit-keyring.deb
        # dpkg -i /tmp/linbit-keyring.deb
        # PVERS=8 && echo "deb [signed-by=/etc/apt/trusted.gpg.d/linbit-keyring.gpg] http://packages.linbit.com/public/ proxmox-$PVERS drbd-9" > /etc/apt/sources.list.d/linbit.list
        # apt update
        # apt -y install drbd-dkms drbd-utils linstor-client linstor-controller linstor-satellite linstor-proxmox
        # linstor node create $NODE $NODE_IP --node-type combined
        # TODO: Add other commands necessary for configuring LINSTOR on the node


class DiscoveryService:
    """Service for discovering and managing Proxmox resources."""

    NodeManagement = NodeManagement

    def __init__(self) -> None:
        """Initialize the Discovery Service."""
        self.cluster = ProxmoxCluster()
        self.networks = ProxmoxNetworks()
        self.appliances = ProxmoxAppliances()

    def discover_cluster(self) -> ClusterManifest | None:
        """Discover and return cluster configuration."""
        invalid_node_count = 2
        status = self.cluster.get_status()
        if len(status.get_nodes()) == invalid_node_count:
            return None
        mtu = self.networks.get_mtu()
        cluster_manifest = status.to_cluster_manifest(
            mtu=mtu,
            reserved_tags=[vnet.tag for vnet in self.networks.list_vnets()],
        )
        ha_status = self.cluster.get_ha_status()
        storage_resources = self.cluster.list_storage_resources()
        for node in status.get_nodes():
            node.maintenance_mode = ha_status.in_maintenance_mode(node=node.name)
            node_manifest = node.to_manifest(storage=storage_resources.get_storage_for_node(node=node.name))
            cluster_manifest.add_node(node=node_manifest)
        return cluster_manifest

    def discover_appliances(self) -> None:
        """Discover and create manifests for stored appliances in the cluster."""
        cluster = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        existing_appliances = BaseApplianceManifest.get_existing()
        for node in cluster.get_nodes():
            for storage in node.spec.storage:
                for appliance in self.appliances.list_stored_appliances(node=node.name, storage=storage.name):
                    manifest = BaseApplianceManifest.create_from_stored_appliance(
                        node_ref=node.to_ref(), appliance=appliance,
                    )
                    if manifest.name not in existing_appliances:
                        manifest.save()
