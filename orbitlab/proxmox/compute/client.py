"""Proxmox Compute Client."""

import ipaddress
from typing import TYPE_CHECKING, Literal

import httpx

from orbitlab.proxmox.base import Proxmox

from .models import InstanceStatus, LXCInterfaces, VMInterfaces, QemuConfig


class ProxmoxCompute(Proxmox):
    """Proxmox Compute (VM/LXC) management client."""

    def get_vm_root_volume_id(self, vmid: int) -> str:
        node = self.get_node_for_vmid(vmid=vmid)
        config = self.get(path=f"/nodes/{node}/qemu/{vmid}/config", model=QemuConfig)
        return config.root_volume_id

    def get_lxc_status(self, vmid: int | str) -> Literal["stopped", "running"]:
        node = self.get_node_for_vmid(vmid=int(vmid))
        if not node:
            return "stopped"
        response = self.get(f"/nodes/{node}/lxc/{vmid}/status/current", model=InstanceStatus)
        return response.status

    def get_vm_status(self, vmid: int | str) -> Literal["stopped", "running"]:
        node = self.get_node_for_vmid(vmid=int(vmid))
        response = self.get(f"/nodes/{node}/qemu/{vmid}/status/current", model=InstanceStatus)
        return response.status

    def get_lxc_private_ipv4(self, vmid: int) -> ipaddress.IPv4Interface | None:
        """Retrieve the private IPv4 address of an LXC container."""
        node = self.get_node_for_vmid(vmid=vmid)
        interfaces = self.get(f"/nodes/{node}/lxc/{vmid}/interfaces", model=LXCInterfaces)
        return interfaces.get_default_ipv4()

    def get_vm_private_ipv4(self, vmid: int) -> ipaddress.IPv4Interface | None:
        """Retrieve the private IPv4 address of an LXC container."""
        node = self.get_node_for_vmid(vmid=vmid)
        try:
            interfaces = self.get(f"/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces", model=VMInterfaces)
        except httpx.HTTPStatusError:
            return None
        return interfaces.get_default_ipv4()

    def _create_pool(self) -> None:
        params = {"poolid": "avp-hf83nd9845h", "comment": "My Pool"}
        self.create("/pools", model=None, **params)

    def _add_vm_to_pool(self) -> None:
        vmid = self.get_next_vmid()
        params = {
            "vmid": vmid,
            "pool": "avp-hf83nd9845h",
            "name": "test",
            "cores": 2,
            "sockets": 1,
            "memory": 2 * 1024,
            "cpu": "x86-64-v2-AES",
            "numa": 0,
            "agent": "enabled=1",
            "serial0": "socket",
            "scsi0": "local:0,import-from=local:import/vmi-fy3tg1vhb9hc.qcow2",
            "ide0": "local:cloudinit",
            "citype": "nocloud",
            "ciuser": "root",
            "cipassword": "asdfasdf",
            "net0": "virtio,bridge=olvn1000",
            "ipconfig0": "gw=192.168.0.1,ip=192.168.0.25/21",
            "searchdomain": "olvn1000.orbitlab.internal",
            "nameserver": "192.168.0.2",
            "scsihw": "virtio-scsi-single",
            "ostype": "l26",
            "onboot": "1",
            "boot": "order=scsi0",
        }
        self.create_vm(node=self.__node__, params=params, disk_size=10, start=True)
