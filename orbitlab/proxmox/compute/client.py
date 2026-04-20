"""Proxmox Compute Client."""

import asyncio
import hashlib
import ipaddress
from pathlib import Path
from string import Template
from typing import Literal

import backoff
import httpx

from orbitlab.proxmox import Proxmox
from orbitlab.proxmox.base.models import QemuConfig, AgentExecPid, AgentExecStatus, Task

from .models import InstanceStatus, LXCInterfaces, VMInterfaces, ProxmoxPools


class ProxmoxCompute(Proxmox):
    """Proxmox Compute (VM/LXC) management client."""

    async def create_vm(self, params: dict, node: str = "") -> None:
        if not node:
            node = self.__node__
        task = await self.create(path=f"/nodes/{node}/qemu", model=Task, **params)
        await self.wait_for_task(task=task)

    async def create_lxc(self, params: dict, node: str = "") -> None:
        if not node:
            node = self.__node__
        task = await self.create(path=f"/nodes/{node}/lxc", model=Task, **params)
        await self.wait_for_task(task=task)

    async def get_lxc_status(self, vmid: int | str) -> Literal["stopped", "running"]:
        node = await self.get_node_for_vmid(vmid=int(vmid))
        if not node:
            return "stopped"
        response = await self.get(f"/nodes/{node}/lxc/{vmid}/status/current", model=InstanceStatus)
        return response.status

    async def get_vm_status(self, vmid: int | str) -> Literal["stopped", "running"]:
        node = await self.get_node_for_vmid(vmid=int(vmid))
        response = await self.get(f"/nodes/{node}/qemu/{vmid}/status/current", model=InstanceStatus)
        return response.status

    async def get_agent_enabled(self, vmid: int) -> bool:
        node = await self.get_node_for_vmid(vmid=vmid)
        config = await self.get(f"/nodes/{node}/qemu/{vmid}/config", model=QemuConfig)
        return config.agent_enabled

    async def wait_for_agent(self, vmid: int) -> None:
        """Wait for the guest agent on a virtual machine to become available."""
        node = await self.get_node_for_vmid(vmid=vmid)
        async with asyncio.timeout(30):
            while True:
                try:
                    await self.create(path=f"/nodes/{node}/qemu/{vmid}/agent/ping", model=None)
                except httpx.HTTPStatusError:
                    await asyncio.sleep(2)
                else:
                    break

    async def agent_write_file(self, vmid: int, source: Path, destination: Path) -> None:
        node = await self.get_node_for_vmid(vmid=vmid)
        params = {"content": source.read_text(), "file": str(destination)}
        await self.create(path=f"/nodes/{node}/qemu/{vmid}/agent/file-write", model=None, **params)

    async def agent_execute_script(self, vmid: int, script: str) -> AgentExecStatus:
        node = await self.get_node_for_vmid(vmid=vmid)
        filename = f"/tmp/{hashlib.md5(script.encode()).hexdigest()}.sh"  # noqa: S324
        script_template = Template("#!/bin/bash\nset -euo pipefail\n$content\nrm -f $filename\n")

        await self.create(
            path=f"/nodes/{node}/qemu/{vmid}/agent/file-write",
            model=None,
            content=script_template.safe_substitute(content=script, filename=filename),
            file=filename,
        )

        pid_response = await self.create(
            path=f"/nodes/{node}/qemu/{vmid}/agent/exec",
            model=AgentExecPid,
            command=["bash", filename],
        )
        status = await self.get(
            path=f"/nodes/{node}/qemu/{vmid}/agent/exec-status",
            model=AgentExecStatus,
            pid=pid_response.pid,
        )
        while not status.exited:
            await asyncio.sleep(2)
            status = await self.get(
                path=f"/nodes/{node}/qemu/{vmid}/agent/exec-status",
                model=AgentExecStatus,
                pid=pid_response.pid,
            )
        return status

    @backoff.on_predicate(backoff.fibo, max_value=13, max_tries=3)
    async def get_ipv4_address(self, vmid: int) -> ipaddress.IPv4Interface | None:
        """Retrieve the private IPv4 address for the given LXC VMID."""
        node = await self.get_node_for_vmid(vmid=vmid)
        try:
            interfaces = await self.get(
                path=f"/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces",
                model=VMInterfaces,
            )
        except httpx.HTTPStatusError:
            return None
        return interfaces.get_default_ipv4()

    async def get_lxc_private_ipv4(self, vmid: int) -> ipaddress.IPv4Interface | None:
        """Retrieve the private IPv4 address of an LXC container."""
        node = await self.get_node_for_vmid(vmid=vmid)
        interfaces = await self.get(f"/nodes/{node}/lxc/{vmid}/interfaces", model=LXCInterfaces)
        return interfaces.get_default_ipv4()

    async def get_vm_private_ipv4(self, vmid: int) -> ipaddress.IPv4Interface | None:
        """Retrieve the private IPv4 address of an LXC container."""
        node = await self.get_node_for_vmid(vmid=vmid)
        try:
            interfaces = await self.get(f"/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces", model=VMInterfaces)
        except httpx.HTTPStatusError:
            return None
        return interfaces.get_default_ipv4()

    async def resize_disk(self, vmid: int, disk_size: int, *, disk_id: str = "scsi0") -> None:
        if node := await self.get_node_for_vmid(vmid=vmid):
            task = await self.set(
                path=f"/nodes/{node}/qemu/{vmid}/resize",
                model=Task,
                disk=disk_id,
                size=f"{disk_size}G",
            )
            await self.wait_for_task(task=task)

    async def start(self, vmid: int) -> None:
        if node := await self.get_node_for_vmid(vmid=vmid):
            task = await self.create(path=f"/nodes/{node}/qemu/{vmid}/status/start", model=Task)
            await self.wait_for_task(task=task)

    async def stop(self, vmid: int) -> None:
        if node := await self.get_node_for_vmid(vmid=vmid):
            task = await self.create(path=f"/nodes/{node}/qemu/{vmid}/status/stop", model=Task)
            await self.wait_for_task(task=task)

    async def shutdown(self, vmid: int) -> None:
        if node := await self.get_node_for_vmid(vmid=vmid):
            task = await self.create(path=f"/nodes/{node}/qemu/{vmid}/status/shutdown", model=Task)
            await self.wait_for_task(task=task)

    async def reboot(self, vmid: int) -> None:
        if node := await self.get_node_for_vmid(vmid=vmid):
            task = await self.create(path=f"/nodes/{node}/qemu/{vmid}/status/reboot", model=Task)
            await self.wait_for_task(task=task)

    async def terminate(self, vmid: int) -> None:
        if node := await self.get_node_for_vmid(vmid=vmid):
            task = await self.create(path=f"/nodes/{node}/qemu/{vmid}/status/shutdown", model=Task)
            await self.wait_for_task(task=task)
            params = {"destroy-unreferenced-disks": 1, "purge": 1}
            task = await self.delete(path=f"/nodes/{node}/qemu/{vmid}", model=Task, **params)
            await self.wait_for_task(task=task)

    async def move_disk(self, from_vmid: int, to_vmid: int, disk_id: str, target_disk_id: str = "") -> None:
        if not target_disk_id:
            target_disk_id = disk_id

        node = await self.get_node_for_vmid(vmid=from_vmid)
        params = {"disk": "scsi1", "target-disk": "scsi1", "target-vmid": to_vmid}
        task = await self.create(path=f"/nodes/{node}/qemu/{from_vmid}/move_disk", model=Task, **params)
        await self.wait_for_task(task=task)

    async def list_pools(self) -> ProxmoxPools:
        return await self.get(f"/pools", model=ProxmoxPools)

    async def pool_exists(self, pool_id: str) -> bool:
        pools = await self.list_pools()
        return bool(pools.get_pool_by_id(pool_id=pool_id))

    async def create_pool(self, pool_id: str, alias: str) -> None:
        if await self.pool_exists(pool_id=pool_id):
            return
        params = {"poolid": pool_id, "comment": alias}
        await self.create("/pools", model=None, **params)

    async def delete_pool(self, pool_id: str) -> None:
        if await self.pool_exists(pool_id=pool_id):
            await self.delete(f"/pools/{pool_id}", model=None)
