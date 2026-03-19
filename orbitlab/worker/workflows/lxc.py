"""LXC Workflows."""

import asyncio

from orbitlab.data_types import ComputeState, ComputeStatus
from orbitlab.manifest.compute_instances.lxc import LXCManifest
from orbitlab.web.pages.compute.lxc.instances.states import LXCInstancesTableState
from orbitlab.worker.workflows.utilities import LXCUtils

from .base import Workflow, WorkflowPayload


class LXCPayload(WorkflowPayload):
    """Payload for LXC workflows."""

    manifest: str

    @property
    def redis_name(self) -> str:
        """Generate the Redis key name for the specified LXC manifest."""
        return f"ol:lxc:{self.manifest}"


class LXCCreateV1(Workflow, LXCUtils):
    """Workflow for creating an LXC container using a specified manifest."""

    TYPE: str = "lxc.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[LXCPayload] = LXCPayload
    payload: LXCPayload

    async def validate(self) -> None:
        """Validate the LXC manifest and ensure it is not already assigned a VMID."""
        if self.payload.manifest not in LXCManifest.get_existing():
            await self.fail(f"LXC Manifest {self.payload.manifest} does not exist")
            return

        manifest = LXCManifest.load(name=self.payload.manifest)
        if manifest.metadata.vmid:
            await self.succeed(f"LXC {self.payload.manifest} already assigned VMID {manifest.metadata.vmid}")

    async def provision(self) -> None:
        """Provision the LXC container."""
        await self.redis.hset(name=self.payload.redis_name, key="state", value=ComputeState.STARTING.value)  # pyright: ignore[reportGeneralTypeIssues]
        await self.emit_reflex_events(events=[LXCInstancesTableState.cache_clear("running")])

        manifest = LXCManifest.load(name=self.payload.manifest)
        vmid = self.proxmox_compute.get_next_vmid()
        await self.create(params=manifest.create_lxc_params(vmid=vmid), node=manifest.metadata.node)
        await self.start(vmid=vmid)

    async def finalize(self) -> None:
        """Finalize the LXC container creation by retrieving and storing its IPv4 address."""
        manifest = LXCManifest.load(name=self.payload.manifest)

        max_retries = 3
        retries = 0
        while retries < max_retries:
            ip_address = await self.get_ipv4_address(vmid=manifest.metadata.vmid)
            if ip_address:
                await self.redis.hset(name=self.payload.redis_name, key="ipv4", value=ip_address.with_prefixlen)  # pyright: ignore[reportGeneralTypeIssues]
                break
            await self.log(message=f"Waiting on {self.payload.manifest} IPv4 address...")
            await asyncio.sleep(2)
            retries += 1

        await self.update_state(name=self.payload.redis_name, status=ComputeStatus.START, vmid=manifest.metadata.vmid)
        await self.emit_reflex_events(events=[LXCInstancesTableState.cache_clear("running")])

    async def on_failure(self) -> None:
        """Handle cleanup actions when the workflow fails."""
        if self.payload.manifest in LXCManifest.get_existing():
            manifest = LXCManifest.load(name=self.payload.manifest)
            if manifest.metadata.vmid:
                await self.terminate(vmid=manifest.metadata.vmid)
            await self.redis.hdel(self.payload.redis_name, "state", "ipv4")  # pyright: ignore[reportGeneralTypeIssues]
            await self.log(message=f"Deleting manifest {self.payload.manifest}")
            manifest.delete()
        await self.emit_reflex_events(events=[LXCInstancesTableState.cache_clear("running")])


class LXCStateChangePayload(LXCPayload):
    """Payload for LXC workflows."""

    desired_status: ComputeStatus


class LXCStateChangeV1(Workflow, LXCUtils):
    """Workflow for changing the state of an LXC container."""

    TYPE: str = "lxc.state-change"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[LXCStateChangePayload] = LXCStateChangePayload
    payload: LXCStateChangePayload

    async def validate(self) -> None:
        """Validate the current state of the LXC container and ensure the desired state change is possible."""
        if self.payload.manifest not in LXCManifest.get_existing():
            await self.fail(f"LXC Manifest {self.payload.manifest} does not exist.")
            return

        manifest = LXCManifest.load(name=self.payload.manifest)

        status = self.proxmox_compute.get_lxc_status(vmid=manifest.metadata.vmid)
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
        manifest = LXCManifest.load(name=self.payload.manifest)
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
        """Finalize the state change of the LXC container and clean up if terminated."""
        manifest = LXCManifest.load(name=self.payload.manifest)

        if self.payload.desired_status == ComputeStatus.TERMINATE:
            manifest.delete()
            await self.redis.hdel(self.payload.redis_name, "state", "ipv4")  # pyright: ignore[reportGeneralTypeIssues]
            await self.emit_reflex_events(events=[LXCInstancesTableState.cache_clear("running")])
        else:
            await self.update_state(
                name=self.payload.redis_name, status=self.payload.desired_status, vmid=manifest.metadata.vmid,
            )
