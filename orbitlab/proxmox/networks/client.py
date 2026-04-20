"""Proxmox Networking Client."""

from pydantic import RootModel

from orbitlab.constants import NetworkSettings
from orbitlab.proxmox.base import Proxmox

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

    async def __apply_changes__(self) -> None:
        """Apply SDN configuration changes to the cluster."""
        await self.set(path="/cluster/sdn")

    async def get_mtu(self) -> int:
        """Get the MTU (Maximum Transmission Unit) of the vmbr0 network interface."""
        async with await self.create_connection(node=self.__node__) as connection:
            output = await connection.run_command(command="cat /sys/class/net/vmbr0/mtu", check_output=True)
        return int(output)

    async def describe_evpn_controller(self) -> EVPNController | None:
        """Get details of an EVPN controller."""
        params = {"pending": 1, "running": 1, "type": "evpn"}
        controllers = await self.get(path="/cluster/sdn/controllers", model=RootModel[list[EVPNController]], **params)
        if not controllers.root:
            return None
        return next(iter(controllers.root))

    async def describe_backplane(self) -> DescribeBackplane:
        """Describe the OrbitLab Backplane network."""
        subnets = await self.get(path=f"/cluster/sdn/vnets/{NetworkSettings.BACKPLANE.NAME}/subnets", model=Subnets)
        subnet = subnets.get_first()
        vnet = await self.get(path=f"/cluster/sdn/vnets/{subnet.vnet}", model=VNet)
        zone = await self.get(path=f"/cluster/sdn/zones/{vnet.zone}", model=BackplaneZone)
        controller = await self.get(path=f"/cluster/sdn/controllers/{zone.controller}", model=EVPNController)
        return DescribeBackplane(zone=zone, vnet=vnet, controller=controller, subnet=subnet)

    async def list_sectors(self) -> list[DescribeSector]:
        """List existing Sectors."""
        sectors = []
        vnets = await self.list_vnets()
        for vnet in vnets.root:
            if not vnet.name.startswith("olvn"):
                continue
            subnets = await self.get(path=f"/cluster/sdn/vnets/{vnet.name}/subnets", model=Subnets)
            sector_network = subnets.get_cidr()
            bridges = await self.get(path=f"/nodes/{self.__node__}/sdn/zones/{vnet.name}/bridges", model=ZoneBridges)
            gateway_vmid = 0
            assignments = {}
            for vm in bridges.get_vms():
                if not vm.vmid:
                    continue
                instance = await self.get(path=f"/nodes/{self.__node__}/lxc/{vm.vmid}/config", model=ComputeConfig)
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

    # async def create_backplane(self, backplane: ClusterManifest) -> None:
    #     """Create the backplane network configuration."""
    #     controller_params = {
    #         "controller": cluster.spec.backplane.controller.id,
    #         "type": "evpn",
    #         "asn": cluster.spec.backplane.controller.asn,
    #         "peers": cluster.spec.backplane.controller.peer_list,
    #     }
    #     await self.create(path="/cluster/sdn/controllers", model=None, **controller_params)
    #     zone_params = {
    #         "type": "evpn",
    #         "zone": cluster.spec.backplane.zone_id,
    #         "controller": cluster.spec.backplane.controller.id,
    #         "vrf_vxlan": cluster.spec.backplane.zone_tag,
    #         "advertise-subnets": 1,
    #         "mtu": cluster.spec.backplane.mtu,
    #         "ipam": "pve",
    #         "exitnodes": cluster.exit_nodes,
    #     }
    #     await self.create(path="/cluster/sdn/zones", model=None, **zone_params)
    #     vnet_params = {
    #         "vnet": cluster.spec.backplane.vnet_id,
    #         "zone": cluster.spec.backplane.zone_id,
    #         "alias": NetworkSettings.BACKPLANE.ALIAS,
    #         "tag": cluster.spec.backplane.vnet_tag,
    #     }
    #     await self.create("/cluster/sdn/vnets", model=None, **vnet_params)
    #     subnet_params = {
    #         "subnet": cluster.spec.backplane.cidr_block.with_prefixlen,
    #         "gateway": str(cluster.spec.backplane.gateway_address),
    #         "type": "subnet",
    #         "snat": 1,
    #     }
    #     await self.create(f"/cluster/sdn/vnets/{cluster.spec.backplane.vnet_id}/subnets", model=None, **subnet_params)
    #     await self.__apply_changes__()

    async def list_vnets(self) -> VNetList:
        """List all virtual networks (VNets) in the cluster."""
        return await self.get(path="/cluster/sdn/vnets", model=VNetList)

    async def list_attached(self, sector_id: str) -> list[AttachedInstances]:
        """List all compute instances attached to a specific sector network."""
        bridges = await self.get(path=f"/nodes/{self.__node__}/sdn/zones/{sector_id}/bridges", model=ZoneBridges)
        instances = []
        for vm in bridges.get_vms():
            if not vm.vmid:
                continue
            if vm.compute_type == "qemu":
                instances.append(AttachedInstances(vmid=vm.vmid, compute_type="qemu"))
                continue
            instance = await self.get(path=f"/nodes/{self.__node__}/lxc/{vm.vmid}/config", model=ComputeConfig)
            if not instance.is_orbitlab_infra:
                instances.append(AttachedInstances(vmid=vm.vmid, compute_type="lxc"))
        return instances
