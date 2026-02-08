"""Proxmox Networking Client."""

from pydantic import RootModel

from orbitlab.clients.proxmox.base import Proxmox, Task
from orbitlab.constants import NetworkSettings
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.services.pki.client import SecretVault

from .models import (
    BackplaneZone,
    ClusterVMResources,
    ComputeConfig,
    DescribeBackplane,
    DescribeSector,
    EVPNController,
    SectorAttachedInstances,
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

    def list_vms(self, sector: SectorManifest):
        params = {"type": "vm"}
        for vm in self.get(path="/cluster/resources", model=ClusterVMResources, **params).list_non_gw_vms():
            instance = self.get(path=f"/nodes/{vm.node}/lxc/{vm.vmid}/config", model=None)
            if not isinstance(instance, dict):
                raise TypeError
            compute = {
                "vmid": vm.vmid,
                "ip": ""
            }
            # TODO: FINISH

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
        subnets = self.get(path=f"/cluster/sdn/vnets/{NetworkSettings.BACKPLANE.NAME}/subnets", model=Subnets)
        subnet = subnets.get_first()
        vnet = self.get(path=f"/cluster/sdn/vnets/{subnet.vnet}", model=VNet)
        zone = self.get(path=f"/cluster/sdn/zones/{vnet.zone}", model=BackplaneZone)
        controller = self.get(path=f"/cluster/sdn/controllers/{zone.controller}", model=EVPNController)
        return DescribeBackplane(zone=zone, vnet=vnet, controller=controller, subnet=subnet)

    def list_sectors(self) -> list[DescribeSector]:
        sectors = []
        for vnet in self.list_vnets():
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
            "gateway": str(cluster.spec.backplane.gateway),
            "type": "subnet",
            "vnet": cluster.spec.backplane.vnet_id,
            "snat": 1,
        }
        self.create(f"/cluster/sdn/vnets/{NetworkSettings.BACKPLANE.NAME}/subnets", model=None, **subnet_params)
        self.__apply_changes__()

    def list_vnets(self) -> list[VNet]:
        """List all virtual networks (VNets) in the cluster."""
        return self.get(path="/cluster/sdn/vnets", model=VNetList).root

    def create_sector(self, sector: SectorManifest) -> None:
        """Create a new sector network with associated gateway container."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))

        zone_params = {
            "type": "vxlan",
            "zone": sector.name,
            "peers": ",".join([str(peer) for peer in cluster_manifest.spec.backplane.controller.peers]),
            "mtu": cluster_manifest.spec.backplane.mtu,
        }
        self.create(path="/cluster/sdn/zones", model=None, **zone_params)
        vnet_params = {
            "vnet": sector.name,
            "zone": sector.name,
            "alias": sector.metadata.alias,
            "tag": sector.metadata.tag,
        }
        self.create("/cluster/sdn/vnets", model=None, **vnet_params)
        subnet_params = {
            "subnet": str(sector.spec.cidr_block),
            "gateway": str(sector.default_gateway.ip),
            "type": "subnet",
            "vnet": sector.name,
        }
        self.create(f"/cluster/sdn/vnets/{sector.name}/subnets", model=None, **subnet_params)
        self.__apply_changes__()

    def create_sector_gateway(self, sector: SectorManifest) -> None:
        """Create and configure a sector gateway LXC container on Proxmox for the given sector."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))

        vmid = self.get_next_vmid()
        backplane_address = cluster_manifest.assign_ip(vmid=vmid)

        params = {
            "features": "nesting=1",
            "ostemplate": f"local:vztmpl/{cluster_manifest.metadata.sector_gateway_appliance}",
            "hostname": sector.gateway_name,
            "cores": "1",
            "memory": "512",
            "swap": "512",
            "net0": f"name=eth0,bridge={sector.name}",
            "net1": (
                "name=eth1,"
                f"bridge={cluster_manifest.spec.backplane.vnet_id},"
                f"ip={backplane_address},"
                f"gw={cluster_manifest.spec.backplane.gateway}"
            ),
            "net2": (
                "name=eth2,"
                f"bridge={sector.name},"
                f"ip={sector.dns_address.with_prefixlen},"
                f"gw={sector.default_gateway.ip}"
            ),
            "rootfs": "local-zfs:8",
            "unprivileged": "1",
            "vmid": vmid,
            "ssh-public-keys": "",
            "password": SecretVault.generate_random_password(),
            "searchdomain": f"{sector.name}.orbitlab.internal",
            "onboot": "1",
        }
        task = self.create(path=f"/nodes/{self.__node__}/lxc", model=Task, **params)
        sector.set_gateway(vmid=vmid)
        self.wait_for_task(task=task)
        task = self.create(path=f"/nodes/{self.__node__}/lxc/{vmid}/status/start", model=Task)
        self.wait_for_task(task=task)
        conn = self.create_connection(node=self.__node__)
        gateway_configure_command = (
            f"/usr/local/bin/sgwtool --sector-cidr {sector.spec.cidr_block} "
            f"--backplane-cidr {cluster_manifest.spec.backplane.cidr_block} --backplane-address {backplane_address.ip}"
        )
        conn.lxc_execute_script(vmid=vmid, content=gateway_configure_command)

    def delete_sector(self, sector: SectorManifest) -> None:
        """Delete a sector network and its associated gateway container."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        if sector.spec.gateway_vmid:
            params = {"destroy-unreferenced-disks": 1, "force": 1, "purge": 1}
            task = self.delete(path=f"/nodes/{self.__node__}/lxc/{sector.spec.gateway_vmid}", model=Task, **params)
            self.wait_for_task(task=task)
            cluster_manifest.release_ip(vmid=sector.spec.gateway_vmid)

        subnet_id = str(sector.spec.cidr_block).replace("/", "-")
        self.delete(f"/cluster/sdn/vnets/{sector.name}/subnets/{sector.name}-{subnet_id}", model=None)
        self.delete(path=f"/cluster/sdn/vnets/{sector.name}", model=None)
        self.delete(path=f"/cluster/sdn/zones/{sector.name}", model=None)
        self.__apply_changes__()

    def list_attached(self, sector_id: str) -> SectorAttachedInstances:
        """List all compute instances attached to a specific sector network."""
        sector = SectorManifest.load(name=sector_id)
        bridges = self.get(path=f"/nodes/{self.__node__}/sdn/zones/{sector_id}/bridges", model=ZoneBridges)
        instances: dict[int, ComputeConfig] = {}
        for vm in bridges.get_vms():
            if not vm.vmid:
                continue
            instance = self.get(path=f"/nodes/{self.__node__}/lxc/{vm.vmid}/config", model=ComputeConfig)
            if not instance.is_orbitlab_infra:
                instances[vm.vmid] = instance
        return SectorAttachedInstances.create(sector=sector, instances=instances)
