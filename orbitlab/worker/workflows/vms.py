"""VM Workflows."""

import asyncio
from typing import Annotated

from orbitlab.data_types import ComputeStatus, ProxmoxComputeStatus, SerializeEnum
from orbitlab.proxmox import ProxmoxCompute
from orbitlab.redis.clients import VMClient
from orbitlab.web.global_state import OrbitLabState

from .base import Workflow, WorkflowPayload


class VMPayload(WorkflowPayload):
    """Default payload for VM workflows."""

    id: str


class VMCreateV1(Workflow):
    """Workflow for creating an VM instance."""

    TYPE: str = "vm.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[VMPayload] = VMPayload
    payload: VMPayload

    async def validate(self) -> None:
        instance = await VMClient().get_instance(id=self.payload.id)
        if instance.state.vmid:
            return await self.succeed(f"VM {self.payload.id} already assigned VMID {instance.state.vmid}")

    async def provision(self) -> None:
        """Provision the VM instance by creating and starting it."""
        proxmox = ProxmoxCompute()
        client = VMClient()
        instance = await client.get_instance(id=self.payload.id)
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_vm_create_params(id=instance.config.id, vmid=vmid)
        
        await self.log(message=f"Creating {vmid}@{instance.config.node} with params: {self._redact_params(params=params)}")
        await proxmox.create_vm(params=params, node=instance.config.node)
        
        await self.log(message=f"Resizing scsi0 on {vmid}@{instance.config.node} to: {instance.config.disk_size}G")
        await asyncio.sleep(1)  # Take a beat so Proxmox doesn't panic when trying to resize the disk after creation
        await proxmox.resize_disk(vmid=vmid, disk_size=instance.config.disk_size)
        
        await self.log(message=f"Starting {vmid}@{instance.config.node}")
        await proxmox.start(vmid=vmid)

    async def finalize(self) -> None:
        """Finalize the VM creation by retrieving and storing the IPv4 address."""
        await self._create_new_workflow(workflow=AquireVMIpAddress, payload=self.payload.copy_payload())
        await VMClient().set_instance_status(id=self.payload.id, status=ComputeStatus.RUNNING)
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("vm_instances")])


class AquireVMIpAddress(Workflow):
    """Workflow for acquiring an IPv4 address for a VM instance."""

    TYPE: str = "vm.acquire-ip"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[VMPayload] = VMPayload
    payload: VMPayload

    async def validate(self) -> None:
        """Validate that the VM has qemu guest agent enabled."""
        instance = await VMClient().get_instance(id=self.payload.id)
        if not await ProxmoxCompute().get_agent_enabled(vmid=instance.state.vmid):
            await self.fail(error=f"Guest Agent not enabled for {self.payload.id}")

    async def provision(self) -> None:
        """Provision the LXC container."""
        instance = await VMClient().get_instance(id=self.payload.id)
        proxmox = ProxmoxCompute()
        max_retries = 3
        retries = 0
        while retries < max_retries:
            if address := await proxmox.get_vm_private_ipv4(vmid=instance.state.vmid):
                return await VMClient().set_instance_address(id=self.payload.id, address=address)
            retries += 1
            await self.log(level="Info", message=f"Acquiring IPv4 address for {self.payload.id} retry {retries}")
        await self.fail(error=f"Max retries exceeded attempting to aquire IPv4 address for {self.payload.id}")

    async def on_succeed(self) -> None:
        """Handle actions to perform when the workflow succeeds."""
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("vm_instances")])


class VMStateChangePayload(VMPayload):
    """Payload for VM state change events."""

    desired_status: Annotated[ProxmoxComputeStatus, SerializeEnum]


class VMStateChangeV1(Workflow):
    """Workflow for changing the state of an VM instance."""

    TYPE: str = "vm.state-change"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[VMStateChangePayload] = VMStateChangePayload
    payload: VMStateChangePayload

    async def validate(self) -> None:
        """Validate the current state of the VM and ensure the desired state change is possible."""
        client = VMClient()
        instance = await client.get_instance(id=self.payload.id)

        status = await ProxmoxCompute().get_vm_status(vmid=instance.state.vmid)
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
        instance = await VMClient().get_instance(id=self.payload.id)
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
        """Finalize the state change by updating or cleaning up its state."""
        if self.payload.desired_status == ProxmoxComputeStatus.TERMINATE:
            VMClient().delete_instance(id=self.payload.id)
