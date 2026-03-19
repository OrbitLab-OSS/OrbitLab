"""Proxmox Networking Client."""

from pydantic import RootModel

from orbitlab.constants import NetworkSettings
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.proxmox.base import Proxmox, Task

from .models import (
    AttachedInstances,
    BackplaneZone,
    ComputeConfig,
    DescribeBackplane,
    DescribeSector,
    EVPNController,
    Subnets,
    VNet,
    VNetList,
    ZoneBridges,
)


class ProxmoxNetworks(Proxmox):
    """Proxmox SDN (Software Defined Networking) management client."""

    def __apply_changes__(self) -> None:
        """Apply SDN configuration changes to the cluster."""
        self.set(path="/cluster/sdn")

    def get_mtu(self) -> int:
        """Get the MTU (Maximum Transmission Unit) of the vmbr0 network interface."""
        remote_connection = self.create_connection(node=self.__node__)
        output = remote_connection.run_command(command="cat /sys/class/net/vmbr0/mtu", check_output=True)
        return int(output.decode())

    def describe_evpn_controller(self) -> EVPNController | None:
        """Get details of an EVPN controller."""
        params = {"pending": 1, "running": 1, "type": "evpn"}
        controllers = self.get(path="/cluster/sdn/controllers", model=RootModel[list[EVPNController]], **params).root
        if not controllers:
            return None
        return next(iter(controllers))

    def update_evpn_controller(self, cluster: ClusterManifest) -> None:
        """Update an existing EVPN controller with new peer nodes."""
        params = {"peers": cluster.spec.backplane.controller.peer_list}
        self.set(path=f"/cluster/sdn/controllers/{cluster.spec.backplane.controller.id}", model=None, **params)
        self.__apply_changes__()

    def describe_backplane(self) -> DescribeBackplane:
        """Describe the OrbitLab Backplane network."""
        subnets = self.get(path=f"/cluster/sdn/vnets/{NetworkSettings.BACKPLANE.NAME}/subnets", model=Subnets)
        subnet = subnets.get_first()
        vnet = self.get(path=f"/cluster/sdn/vnets/{subnet.vnet}", model=VNet)
        zone = self.get(path=f"/cluster/sdn/zones/{vnet.zone}", model=BackplaneZone)
        controller = self.get(path=f"/cluster/sdn/controllers/{zone.controller}", model=EVPNController)
        return DescribeBackplane(zone=zone, vnet=vnet, controller=controller, subnet=subnet)

    def list_sectors(self) -> list[DescribeSector]:
        """List existing Sectors."""
        sectors = []
        for vnet in self.list_vnets().root:
            if not vnet.name.startswith("olvn"):
                continue
            subnets = self.get(path=f"/cluster/sdn/vnets/{vnet.name}/subnets", model=Subnets)
            sector_network = subnets.get_cidr()
            bridges = self.get(path=f"/nodes/{self.__node__}/sdn/zones/{vnet.name}/bridges", model=ZoneBridges)
            gateway_vmid = 0
            assignments = {}
            for vm in bridges.get_vms():
                if not vm.vmid:
                    continue
                instance = self.get(path=f"/nodes/{self.__node__}/lxc/{vm.vmid}/config", model=ComputeConfig)
                if address := instance.get_sector_address(sector_network):
                    assignments[vm.vmid] = address
            sectors.append(
                DescribeSector(
                    vnet=vnet,
                    subnets=subnets,
                    gateway_vmid=gateway_vmid,
                    assignments=assignments,
                ),
            )
        return sectors

    def create_backplane(self, cluster: ClusterManifest) -> None:
        """Create the backplane network configuration."""
        controller_params = {
            "controller": cluster.spec.backplane.controller.id,
            "type": "evpn",
            "asn": cluster.spec.backplane.controller.asn,
            "peers": cluster.spec.backplane.controller.peer_list,
        }
        self.create(path="/cluster/sdn/controllers", model=None, **controller_params)
        zone_params = {
            "type": "evpn",
            "zone": cluster.spec.backplane.zone_id,
            "controller": cluster.spec.backplane.controller.id,
            "vrf_vxlan": cluster.spec.backplane.zone_tag,
            "advertise-subnets": 1,
            "mtu": cluster.spec.backplane.mtu,
            "ipam": "pve",
            "exitnodes": cluster.exit_nodes,
        }
        self.create(path="/cluster/sdn/zones", model=None, **zone_params)
        vnet_params = {
            "vnet": cluster.spec.backplane.vnet_id,
            "zone": cluster.spec.backplane.zone_id,
            "alias": NetworkSettings.BACKPLANE.ALIAS,
            "tag": cluster.spec.backplane.vnet_tag,
        }
        self.create("/cluster/sdn/vnets", model=None, **vnet_params)
        subnet_params = {
            "subnet": cluster.spec.backplane.cidr_block.with_prefixlen,
            "gateway": str(cluster.spec.backplane.gateway_address),
            "type": "subnet",
            "snat": 1,
        }
        self.create(f"/cluster/sdn/vnets/{cluster.spec.backplane.vnet_id}/subnets", model=None, **subnet_params)
        self.__apply_changes__()

    def list_vnets(self) -> VNetList:
        """List all virtual networks (VNets) in the cluster."""
        return self.get(path="/cluster/sdn/vnets", model=VNetList)

    def create_sector(self, manifest: SectorManifest) -> None:
        """Create a new sector network."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))

        zone_params = {
            "type": "vxlan",
            "zone": manifest.name,
            "peers": ",".join([str(peer) for peer in cluster_manifest.spec.backplane.controller.peers]),
            "mtu": cluster_manifest.spec.backplane.mtu,
        }
        self.create(path="/cluster/sdn/zones", model=None, **zone_params)
        vnet_params = {
            "vnet": manifest.name,
            "zone": manifest.name,
            "alias": manifest.spec.alias,
            "tag": manifest.spec.tag,
        }
        self.create("/cluster/sdn/vnets", model=None, **vnet_params)
        subnet_params = {
            "subnet": manifest.spec.cidr_block.with_prefixlen,
            "gateway": str(manifest.default_gateway.ip),
            "type": "subnet",
        }
        self.create(f"/cluster/sdn/vnets/{manifest.name}/subnets", model=None, **subnet_params)
        self.__apply_changes__()

    def delete_sector(self, manifest: SectorManifest) -> None:
        """Delete a sector network and its associated gateway container."""
        if manifest.metadata.gateway_vmid:
            params = {"destroy-unreferenced-disks": 1, "force": 1, "purge": 1}
            task = self.delete(
                path=f"/nodes/{self.__node__}/lxc/{manifest.metadata.gateway_vmid}", model=Task, **params,
            )
            self.wait_for_task(task=task)

        subnet_id = str(manifest.spec.cidr_block).replace("/", "-")
        self.delete(f"/cluster/sdn/vnets/{manifest.name}/subnets/{manifest.name}-{subnet_id}", model=None)
        self.delete(path=f"/cluster/sdn/vnets/{manifest.name}", model=None)
        self.delete(path=f"/cluster/sdn/zones/{manifest.name}", model=None)
        self.__apply_changes__()

    def list_attached(self, sector_id: str) -> list[AttachedInstances]:
        """List all compute instances attached to a specific sector network."""
        bridges = self.get(path=f"/nodes/{self.__node__}/sdn/zones/{sector_id}/bridges", model=ZoneBridges)
        instances = []
        for vm in bridges.get_vms():
            if not vm.vmid:
                continue
            if vm.compute_type == "qemu":
                instances.append(AttachedInstances(vmid=vm.vmid, compute_type="qemu"))
                continue
            instance = self.get(path=f"/nodes/{self.__node__}/lxc/{vm.vmid}/config", model=ComputeConfig)
            if not instance.is_orbitlab_infra:
                instances.append(AttachedInstances(vmid=vm.vmid, compute_type="lxc"))
        return instances
