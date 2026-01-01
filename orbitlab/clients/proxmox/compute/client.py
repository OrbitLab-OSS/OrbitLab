"""Proxmox Compute Client."""

from ipaddress import IPv4Address

from orbitlab.clients.proxmox.base import Proxmox, Task
from orbitlab.data_types import LXCStatus
from orbitlab.manifest.lxc import LXCManifest
from orbitlab.manifest.sector import SectorManifest


class ProxmoxCompute(Proxmox):
    """Proxmox Compute (VM/LXC) management client."""

    def __add_sector_record__(self, sector: SectorManifest, hostname: str, ip: IPv4Address) -> None:
        """Add a DNS record for the given hostname and IP in the sector's DNS container."""
        if sector.spec.dns_vmid:
            conn = self.create_connection(node=self.__node__)
            conn.lxc_execute_script(vmid=sector.spec.dns_vmid, content=f"/usr/bin/dnstool record add {hostname} {ip}")

    def __delete_sector_record__(self, sector: SectorManifest, hostname: str) -> None:
        """Delete a DNS record for the given hostname in the sector's DNS container."""
        if sector.spec.dns_vmid:
            conn = self.create_connection(node=self.__node__)
            conn.lxc_execute_script(vmid=sector.spec.dns_vmid, content=f"/usr/bin/dnstool record delete {hostname}")

    def launch_lxc(self, lxc: LXCManifest) -> None:
        """Create an LXC compute resource."""
        vmid = self.get_next_vmid()
        sector = SectorManifest.load(name=lxc.spec.sector_id)
        address = sector.get_ipam().assign_ip(subnet_name=lxc.spec.subnet_name, vmid=vmid)
        gateway = sector.get_subnet(name=lxc.spec.subnet_name).default_gateway
        params = {
            "features": "nesting=1",
            "ostemplate": lxc.spec.os_template,
            "hostname": lxc.metadata.hostname,
            "cores": lxc.spec.cores,
            "memory": lxc.spec.memory * 1024,
            "swap": lxc.spec.memory * 1024,
            "net0": (
                "name=eth0,"
                f"bridge={sector.name},"
                f"ip={address.with_prefixlen},"
                f"gw={gateway.ip}"
            ),
            "rootfs": f"{lxc.spec.disk_storage}:{lxc.spec.disk_size}",
            "unprivileged": "1",
            "vmid": vmid,
            "ssh-public-keys": "",  # TODO: Support specific or OrbitLab Ref
            "password": lxc.get_password(),
            "searchdomain": f"{sector.name}.orbitlab.internal",
            "nameserver": f"{sector.dns_address.ip}",
            "onboot": "1" if lxc.metadata.on_boot else "0",
        }
        self.create_lxc(node=lxc.spec.node, params=params, start=True)
        lxc.launched(vmid=vmid, address=address)
        self.__add_sector_record__(sector=sector, hostname=lxc.metadata.hostname, ip=address.ip)

    def set_lxc_status(self, lxc: LXCManifest, status: LXCStatus) -> None:
        """Set the status of an LXC container."""
        task = self.create(path=f"/nodes/{lxc.spec.node}/lxc/{lxc.spec.vmid}/status/{status}", model=Task)
        self.wait_for_task(node=task.node, upid=task.upid)
        lxc.set_status(status=status)
