"""Proxmox Networking Client."""

from ipaddress import IPv4Address, IPv4Network

from pydantic import RootModel

from orbitlab.clients.proxmox.base import Proxmox, Task
from orbitlab.constants import NetworkSettings
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.services.pki.client import SecretVault

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
        if not sector.spec.gateway_vmid:
            raise ValueError
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        backplane_address = cluster_manifest.get_assigned_ip(vmid=sector.spec.gateway_vmid)
        sector_flags = " ".join(
            [f"--sector-subnet-addr {subnet.default_gateway}" for subnet in sector.spec.subnets],
        )
        backplane_flags = (
            f"--backplane-assigned-addr {backplane_address} "
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

    def create_sector_gateway(self, sector: SectorManifest) -> None:
        """Create and configure a sector gateway LXC container on Proxmox for the given sector."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))

        vmid = self.get_next_vmid()
        address = cluster_manifest.assign_ip(vmid=vmid)

        params = {
            "features": "nesting=1",
            "ostemplate": f"local:vztmpl/{cluster_manifest.metadata.sector_gateway_appliance}",
            "hostname": sector.gateway_name,
            "cores": "1",
            "memory": "256",
            "swap": "256",
            "net0": f"name=eth0,bridge={sector.name}",
            "net1": (
                "name=eth1,"
                f"bridge={cluster_manifest.spec.backplane.vnet_id},"
                f"ip={address},"
                f"gw={cluster_manifest.spec.backplane.gateway}"
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
        self.wait_for_task(node=task.node, upid=task.upid)
        task = self.create(path=f"/nodes/{self.__node__}/lxc/{vmid}/status/start", model=Task)
        self.wait_for_task(node=task.node, upid=task.upid)
        conn = self.create_connection(node=self.__node__)
        configure_frr_command = self.__sgwtool_frr_set__(
            sector=sector,
            backplane_gateway=cluster_manifest.spec.backplane.gateway,
        )
        configure_nftables_command = self.__sgwtool_nftables_set__(
            primary_ip=sector.primary_gateway.ip,
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

    def create_sector_dns(self, sector: SectorManifest) -> None:
        """Create and configure a sector DNS LXC container on Proxmox for the given sector."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))

        vmid = self.get_next_vmid()
        address = cluster_manifest.assign_ip(vmid=vmid)

        params = {
            "features": "nesting=1",
            "ostemplate": f"local:vztmpl/{cluster_manifest.metadata.sector_dns_appliance}",
            "hostname": sector.dns_name,
            "cores": "1",
            "memory": "256",
            "swap": "256",
            "net0": (
                "name=eth0,"
                f"bridge={sector.name},"
                f"ip={sector.dns_address.with_prefixlen},"
                f"gw={sector.primary_gateway.ip}"
            ),
            "net1": (
                "name=eth1,"
                f"ip={address.with_prefixlen},"
                f"bridge={cluster_manifest.spec.backplane.vnet_id},"
                f"gw={cluster_manifest.spec.backplane.gateway}"
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
        sector.set_dns(vmid=vmid)
        self.wait_for_task(node=task.node, upid=task.upid)
        task = self.create(path=f"/nodes/{self.__node__}/lxc/{vmid}/status/start", model=Task)
        self.wait_for_task(node=task.node, upid=task.upid)

    def delete_sector(self, sector: SectorManifest) -> None:
        """Delete a sector network and its associated gateway container."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        if sector.spec.gateway_vmid:
            params = {"destroy-unreferenced-disks": 1, "force": 1, "purge": 1}
            task = self.delete(path=f"/nodes/{self.__node__}/lxc/{sector.spec.gateway_vmid}", model=Task, **params)
            self.wait_for_task(node=task.node, upid=task.upid)
            cluster_manifest.release_ip(vmid=sector.spec.gateway_vmid)

        if sector.spec.dns_vmid:
            params = {"destroy-unreferenced-disks": 1, "force": 1, "purge": 1}
            task = self.delete(path=f"/nodes/{self.__node__}/lxc/{sector.spec.dns_vmid}", model=Task, **params)
            self.wait_for_task(node=task.node, upid=task.upid)
            cluster_manifest.release_ip(vmid=sector.spec.dns_vmid)

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
        instances: dict[int, ComputeConfig] = {}
        for vm in bridges.get_vms():
            if not vm.vmid:
                continue
            instance = self.get(path=f"/nodes/{self.__node__}/lxc/{vm.vmid}/config", model=ComputeConfig)
            if not instance.is_orbitlab_infra:
                instances[vm.vmid] = instance
        return SectorAttachedInstances.create(sector=sector, instances=instances)
