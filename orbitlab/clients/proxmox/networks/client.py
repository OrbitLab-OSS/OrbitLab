"""Proxmox Networking Client."""

from ipaddress import IPv4Address, IPv4Network

from pydantic import RootModel

from orbitlab.clients.proxmox.base import Proxmox, Task
from orbitlab.constants import NetworkSettings
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.ipam import IpamManifest
from orbitlab.manifest.secrets import SecretManifest
from orbitlab.manifest.sector import SectorManifest

from .models import (
    ComputeConfig,
    EVPNController,
    SectorAttachedInstances,
    VNet,
    VNetList,
    ZoneBridges,
)


class ProxmoxNetworks(Proxmox):
    """Proxmox SDN (Software Defined Networking) management client."""

    def __apply_changes__(self) -> None:
        """Apply SDN configuration changes to the cluster."""
        self.set(path="/cluster/sdn")

    def __sgwtool_frr_set__(self, sector: SectorManifest, backplane_gateway: IPv4Address) -> str:
        """Generate sgwtool frr set command for configuring FRR routing on the sector gateway."""
        if not sector.spec.gateway:
            raise ValueError
        sector_flags = " ".join(
            [f"--sector-subnet-addr {subnet.default_gateway}" for subnet in sector.spec.subnets],
        )
        backplane_flags = (
            f"--backplane-assigned-addr {sector.spec.gateway.backplane_address} "
            f"--backplane-gw-ip {backplane_gateway}"
        )
        return f"/usr/local/bin/sgwtool frr set {sector_flags}  {backplane_flags}"

    def __sgwtool_nftables_set__(self, primary_ip: IPv4Address, backplane: IPv4Network) -> str:
        """Generate sgwtool nftables set command for configuring nftables on the sector gateway."""
        return f"/usr/local/bin/sgwtool nftables set --primary-sector-ip {primary_ip} --backplane-network {backplane}"

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
        self.set(path=f"/cluster/sdn/controllers/{cluster.spec.backplane.controller.id}", **params)
        self.__apply_changes__()

    def create_backplane(self, cluster: ClusterManifest, *, skip_controller: bool = False) -> None:
        """Create the backplane network configuration."""
        if not skip_controller:
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
        for subnet in sector.spec.subnets:
            subnet_params = {
                "subnet": str(subnet.cidr_block),
                "gateway": str(subnet.default_gateway.ip),
                "type": "subnet",
                "vnet": sector.name,
            }
            self.create(f"/cluster/sdn/vnets/{sector.name}/subnets", model=None, **subnet_params)
        self.__apply_changes__()

        vmid = str(self.get_next_vmid())

        backplane_ipam = IpamManifest.load(name=NetworkSettings.BACKPLANE.IPAM)
        address = backplane_ipam.assign_ip(subnet_name=NetworkSettings.BACKPLANE.NAME, vmid=vmid)

        secret = SecretManifest.create_gateway_password(sector_name=sector.name, sector_tag=sector.metadata.tag)
        params = {
            "features": "nesting=1",
            "ostemplate": f"local:vztmpl/{cluster_manifest.metadata.gateway_appliance}",
            "hostname": sector.gateway_name,
            "cores": "1",
            "memory": "256",
            "swap": "256",
            "net0": f"name=eth0,bridge={sector.name}",
            "net1": (
                f"name=eth1,bridge={cluster_manifest.spec.backplane.vnet_id},ip={address},gw={cluster_manifest.spec.backplane.gateway}"
            ),
            "rootfs": "local-zfs:8",
            "unprivileged": "1",
            "vmid": vmid,
            "ssh-public-keys": "",
            "password": secret.get_current_value(),
            "onboot": "1",
        }
        task = self.create(path=f"/nodes/{self.__node__}/lxc", model=Task, **params)
        sector.set_gateway(backplane_address=address, vmid=vmid, password_ref=secret.to_ref())
        self.wait_for_task(node=task.node, upid=task.upid)
        task = self.create(path=f"/nodes/{self.__node__}/lxc/{vmid}/status/start", model=Task)
        self.wait_for_task(node=task.node, upid=task.upid)
        conn = self.create_connection(node=self.__node__)
        configure_frr_command = self.__sgwtool_frr_set__(
            sector=sector,
            backplane_gateway=cluster_manifest.spec.backplane.gateway,
        )
        configure_nftables_command = self.__sgwtool_nftables_set__(
            primary_ip=sector.primary_gateway,
            backplane=cluster_manifest.spec.backplane.cidr_block,
        )
        conn.lxc_execute_script(
            vmid=vmid,
            content=(
                f"{configure_frr_command}\n"
                f"{configure_nftables_command}\n"
                "/usr/local/bin/sgwtool frr restart\n"
                "/usr/local/bin/sgwtool nftables restart\n"
            ),
        )

    def delete_sector(self, sector: SectorManifest) -> None:
        """Delete a sector network and its associated gateway container."""
        if sector.spec.gateway:
            params = {"destroy-unreferenced-disks": 1, "force": 1, "purge": 1}
            task = self.delete(path=f"/nodes/{self.__node__}/lxc/{sector.spec.gateway.vmid}", model=Task, **params)
            self.wait_for_task(node=task.node, upid=task.upid)

        for subnet in sector.spec.subnets:
            subnet_id = str(subnet.cidr_block).replace("/", "-")
            self.delete(f"/cluster/sdn/vnets/{sector.name}/subnets/{sector.name}-{subnet_id}", model=None)
        self.delete(path=f"/cluster/sdn/vnets/{sector.name}", model=None)
        self.delete(path=f"/cluster/sdn/zones/{sector.name}", model=None)
        self.__apply_changes__()

    def list_attached(self, sector_id: str) -> SectorAttachedInstances:
        """List all compute instances attached to a specific sector network."""
        sector = SectorManifest.load(name=sector_id)
        bridges = self.get(path=f"/nodes/{self.__node__}/sdn/zones/{sector_id}/bridges", model=ZoneBridges)
        instances: dict[str, ComputeConfig] = {}
        for vm in bridges.get_vms():
            if not vm.vmid:
                continue
            instance = self.get(path=f"/nodes/{self.__node__}/lxc/{vm.vmid}/config", model=ComputeConfig)
            if not instance.is_orbitlab_infra:
                instances[vm.vmid] = instance
        return SectorAttachedInstances.create(sector=sector, instances=instances)
