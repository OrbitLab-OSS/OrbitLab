"""VM Workflows."""

from orbitlab.data_types import ComputeState, ComputeStatus
from orbitlab.manifest.compute_instances import VMManifest
from orbitlab.web.pages.compute.vm.instances.states import VMInstancesTableState
from orbitlab.worker.workflows.utilities import VMUtils

from .base import Workflow, WorkflowPayload


class VMPayload(WorkflowPayload):
    """Default payload for VM workflows."""

    manifest: str

    @property
    def redis_name(self) -> str:
        """VM Redis Hash Name."""
        return f"ol:vm:{self.manifest}"


class VMCreateV1(Workflow, VMUtils):
    """Workflow for creating an VM instance."""

    TYPE: str = "vm.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[VMPayload] = VMPayload
    payload: VMPayload

    async def validate(self) -> None:
        """Validate the VM manifest and ensure it is not already assigned a VMID."""
        if self.payload.manifest not in VMManifest.get_existing():
            await self.fail(error=f"Manifest {self.payload.manifest} does not exist")
            return

        manifest = VMManifest.load(name=self.payload.manifest)
        if manifest.metadata.vmid:
            await self.succeed(f"VM {self.payload.manifest} already assigned VMID {manifest.metadata.vmid}")
            return

        await self.set_redis_hash_value(name=self.payload.redis_name, key="state", value=ComputeState.STARTING)
        await self.emit_reflex_events(events=[VMInstancesTableState.cache_clear("running")])

    async def provision(self) -> None:
        """Provision the VM instance by creating and starting it."""
        manifest = VMManifest.load(name=self.payload.manifest)
        vmid = self.proxmox_compute.get_next_vmid()
        await self.create(
            params=manifest.create_vm_params(vmid=vmid),
            node=manifest.metadata.node,
            disk_size=manifest.spec.disk_size,
        )
        await self.start(vmid=vmid)

    async def finalize(self) -> None:
        """Finalize the VM creation by retrieving and storing the IPv4 address."""
        manifest = VMManifest.load(name=self.payload.manifest)

        # Start another workflow to wait for agent/IP
        await self._create_new_workflow(
            workflow=AquireVMIpAddress,
            payload=AquireVMIpAddress.PAYLOAD_TYPE.model_validate({"manifest": self.payload.manifest}),
        )

        await self.update_state(name=self.payload.redis_name, status=ComputeStatus.START, vmid=manifest.metadata.vmid)
        await self.emit_reflex_events(events=[VMInstancesTableState.cache_clear("running")])

    async def on_failure(self) -> None:
        """Handle cleanup actions when the workflow fails."""
        if self.payload.manifest in VMManifest.get_existing():
            manifest = VMManifest.load(name=self.payload.manifest)
            await self.redis.hdel(self.payload.redis_name, "state", "ipv4")
            await self.log(message=f"Deleting manifest {self.payload.manifest}")
            manifest.delete()
            await self.emit_reflex_events(events=[VMInstancesTableState.cache_clear("running")])


class AquireVMIpAddress(Workflow, VMUtils):
    """Workflow for acquiring an IPv4 address for a VM instance."""

    TYPE: str = "vm.acquire-ip"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[VMPayload] = VMPayload
    payload: VMPayload

    async def validate(self) -> None:
        """Validate that the VM has qemu guest agent enabled."""
        if self.payload.manifest not in VMManifest.get_existing():
            await self.fail(f"Manifest {self.payload.manifest} does not exist")
            return

        manifest = VMManifest.load(name=self.payload.manifest)
        if not await self.agent_enabled(vmid=manifest.metadata.vmid):
            await self.fail(f"VM {self.payload.manifest} does not have qemu guest agent enabled")
            return

    async def provision(self) -> None:
        """Provision the LXC container."""
        manifest = VMManifest.load(name=self.payload.manifest)
        max_retries = 3
        retries = 0
        while retries < max_retries:
            ip_address = await self.get_ipv4_address(vmid=manifest.metadata.vmid)
            if ip_address:
                await self.set_redis_hash_value(name=self.payload.redis_name, key="ipv4", value=ip_address.with_prefixlen)
                return
            retries += 1
            await self.log(level="Info", message=f"Acquiring IPv4 address for {manifest.name} retry {retries}")

        await self.fail(error=f"Max retries exceeded attempting to aquire IPv4 address for  {self.payload.manifest}")

    async def on_succeed(self) -> None:
        """Handle actions to perform when the workflow succeeds."""
        await self.emit_reflex_events(events=[VMInstancesTableState.cache_clear("running")])


class VMStateChangePayload(VMPayload):
    """Payload for VM state change events."""

    desired_status: ComputeStatus


class VMStateChangeV1(Workflow, VMUtils):
    """Workflow for changing the state of an VM instance."""

    TYPE: str = "vm.state-change"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[VMStateChangePayload] = VMStateChangePayload
    payload: VMStateChangePayload

    async def validate(self) -> None:
        """Validate the current state of the VM and ensure the desired state change is possible."""
        if self.payload.manifest not in VMManifest.get_existing():
            await self.fail(f"VM Manifest {self.payload.manifest} does not exist")
            return

        manifest = VMManifest.load(name=self.payload.manifest)

        status = self.proxmox_compute.get_vm_status(vmid=manifest.metadata.vmid)
        if status == "stopped" and self.payload.desired_status not in (ComputeStatus.START, ComputeStatus.TERMINATE):
            await self.fail(
                f"VMID {manifest.metadata.vmid} is stopped and cannot be set to {self.payload.desired_status}",
            )
            return

        if status == "running" and self.payload.desired_status == ComputeStatus.START:
            await self.redis.hset(name=self.payload.redis_name, key="state", value=ComputeState.RUNNING.value)
            await self.succeed(f"VMID {manifest.metadata.vmid} already running.")
            return

        await self.update_state(name=self.payload.redis_name, status=self.payload.desired_status)

    async def provision(self) -> None:
        """Change the state of the LXC container to the desired state."""
        manifest = VMManifest.load(name=self.payload.manifest)

        match self.payload.desired_status:
            case ComputeStatus.STOP:
                await self.stop(vmid=manifest.metadata.vmid)
            case ComputeStatus.SHUTDOWN:
                await self.stop(vmid=manifest.metadata.vmid, shutdown=True)
            case ComputeStatus.START:
                await self.start(vmid=manifest.metadata.vmid)
            case ComputeStatus.REBOOT:
                await self.reboot(vmid=manifest.metadata.vmid)
            case ComputeStatus.TERMINATE:
                await self.terminate(vmid=manifest.metadata.vmid)

    async def finalize(self) -> None:
        """Finalize the state change by updating or cleaning up its state."""
        manifest = VMManifest.load(name=self.payload.manifest)

        if self.payload.desired_status == ComputeStatus.TERMINATE:
            manifest.delete()
            await self.redis.hdel(self.payload.redis_name, "state", "ipv4")  # pyright: ignore[reportGeneralTypeIssues]
            await self.emit_reflex_events(events=[VMInstancesTableState.cache_clear("running")])
            return

        await self.update_state(
            name=self.payload.redis_name, status=self.payload.desired_status, vmid=manifest.metadata.vmid,
        )
