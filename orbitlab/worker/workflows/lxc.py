"""LXC Workflows."""

import asyncio

from orbitlab.data_types import ComputeStatus, ProxmoxComputeStatus
from orbitlab.proxmox import ProxmoxCompute
from orbitlab.redis.clients import LXCClient
from orbitlab.web.global_state import OrbitLabState

from .base import Workflow, WorkflowPayload


class LXCPayload(WorkflowPayload):
    """Payload for LXC workflows."""

    id: str


class LXCCreateV1(Workflow):
    """Workflow for creating an LXC container using a specified manifest."""

    TYPE: str = "lxc.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[LXCPayload] = LXCPayload
    payload: LXCPayload

    async def validate(self) -> None:
        """Validate the LXC manifest and ensure it is not already assigned a VMID."""
        if not await LXCClient().instance_exists(id=self.payload.id):
            return await self.fail(f"LXC {self.payload.id} does not exist")

    async def provision(self) -> None:
        """Provision the LXC container."""
        client = LXCClient()
        proxmox = ProxmoxCompute()
        instance = await client.get_instance(id=self.payload.id)
        
        await client.set_instance_status(id=self.payload.id, status=ComputeStatus.STARTING)
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_lxc_create_params(id=self.payload.id, vmid=vmid)
        
        await self.log(f"Creating {self.payload.id} {vmid}@{instance.config.node} with params: {self._redact_params(params)}")
        await proxmox.create_lxc(params=params, node=instance.config.node)
        
        await self.log(f"Starting {self.payload.id} {vmid}@{instance.config.node}")
        await proxmox.start(vmid=vmid)

    async def finalize(self) -> None:
        """Finalize the LXC container creation by retrieving and storing its IPv4 address."""
        client = LXCClient()
        proxmox = ProxmoxCompute()
        instance = await client.get_instance(id=self.payload.id)

        max_retries = 3
        retries = 0
        while retries < max_retries:
            ip_address = await proxmox.get_ipv4_address(vmid=instance.state.vmid)
            if ip_address:
                client.set_instance_address(id=self.payload.id, address=ip_address.ip)
                break
            await self.log(message=f"Waiting on {self.payload.id} IPv4 address...")
            await asyncio.sleep(2)
            retries += 1

        await client.set_instance_status(id=self.payload.id, status=ComputeStatus.RUNNING)
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("lxc_instances")])


class LXCStateChangePayload(LXCPayload):
    """Payload for LXC workflows."""

    desired_status: ProxmoxComputeStatus


class LXCStateChangeV1(Workflow):
    """Workflow for changing the state of an LXC container."""

    TYPE: str = "lxc.state-change"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[LXCStateChangePayload] = LXCStateChangePayload
    payload: LXCStateChangePayload

    async def validate(self) -> None:
        """Validate the current state of the LXC container and ensure the desired state change is possible."""
        client = LXCClient()
        proxmox = ProxmoxCompute()
        
        if not await client.instance_exists(id=self.payload.id):
            return await self.fail(f"LXC {self.payload.id} does not exist.")

        instance = await client.get_instance(id=self.payload.id)

        status = await proxmox.get_lxc_status(vmid=instance.state.vmid)
        if status == "stopped" and self.payload.desired_status not in (ProxmoxComputeStatus.START, ProxmoxComputeStatus.TERMINATE):
            return await self.fail(
                f"VMID {instance.state.vmid} is stopped and cannot be set to {self.payload.desired_status}",
            )
            
        if status == "running" and self.payload.desired_status == ProxmoxComputeStatus.START:
            await client.set_instance_status(id=self.payload.id, status=ComputeStatus.RUNNING)
            return await self.succeed(f"VMID {instance.state.vmid} already running.")
            
        await client.set_instance_status(id=self.payload.id, status=ProxmoxComputeStatus.get_state(status=status))

    async def provision(self) -> None:
        """Change the state of the LXC container to the desired state."""
        instance = await LXCClient().get_instance(id=self.payload.id)
        match self.payload.desired_status:
            case ProxmoxComputeStatus.STOP:
                await ProxmoxCompute().stop(vmid=instance.state.vmid)
            case ProxmoxComputeStatus.SHUTDOWN:
                await ProxmoxCompute().shutdown(vmid=instance.state.vmid)
            case ProxmoxComputeStatus.START:
                await ProxmoxCompute().start(vmid=instance.state.vmid)
            case ProxmoxComputeStatus.REBOOT:
                await ProxmoxCompute().reboot(vmid=instance.state.vmid)
            case ProxmoxComputeStatus.TERMINATE:
                await ProxmoxCompute().terminate(vmid=instance.state.vmid)

    async def finalize(self) -> None:
        """Finalize the state change of the LXC container and clean up if terminated."""
        if self.payload.desired_status == ProxmoxComputeStatus.TERMINATE:
            LXCClient().delete_instance(id=self.payload.id)
