"""DockFS Workflows."""

from ipaddress import IPv4Interface
from typing import Annotated

from orbitlab.data_types import DockFSStatus, SerializeIP
from orbitlab.proxmox import ProxmoxCompute
from orbitlab.redis.clients import DNSClient, DockFSClient
from orbitlab.redis.models import ARecord
from orbitlab.web.global_state import OrbitLabState

from .base import Workflow, WorkflowPayload


class DockFsPayload(WorkflowPayload):
    """DockFS Workflow payload."""

    id: str


class CreateDockFsV1(Workflow):
    """DockFS Create Workflow V1."""

    TYPE: str = "dockfs.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[DockFsPayload] = DockFsPayload
    payload: DockFsPayload

    async def validate(self) -> None:
        """Validate DockFS Manifest data."""
        client = DockFSClient()
        
        if not await client.cluster_exists(id=self.payload.id):
            return await self.fail(f"DockFS {self.payload.id} does not exist")
        
        await client.set_cluster_status(name=self.payload.id, status=DockFSStatus.PENDING)
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("dockfs_clusters")])

    async def provision(self) -> None:
        """Provision the active and passive DockFS nodes."""
        client = DockFSClient()
        proxmox = ProxmoxCompute()
        
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_node_params(id=self.payload.id, vmid=vmid, node_type="active")
        await self.log(f"Creating Active Node {vmid} for {self.payload.id} with params: {self._redact_params(params)}")
        await proxmox.create_vm(params=params)
        await proxmox.start(vmid=vmid)
        
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_node_params(id=self.payload.id, vmid=vmid, node_type="passive")
        await self.log(f"Creating Passive Node {vmid} for {self.payload.id} with params: {self._redact_params(params)}")
        await proxmox.create_vm(params=params)
        await proxmox.start(vmid=vmid)

    async def configure(self) -> None:
        """Configure the active and passive DockFS nodes."""
        client = DockFSClient()
        proxmox = ProxmoxCompute()
        cluster = await client.get_dockfs(id=self.payload.id)
        
        await self.log(f"Configuring {self.payload.id} Active Node {cluster.state.active}")
        await proxmox.wait_for_agent(vmid=cluster.state.active.vmid)
        command = await client.generate_config_command(id=self.payload.id, node_type="active")
        status = await proxmox.agent_execute_script(vmid=cluster.state.active.vmid, script=command)
        if status.exitcode > 0:
            return await self.fail(f"Active Node configuration failed: {status.stderr}")

        await self.log(f"Configuring {self.payload.id} Passive Node {cluster.state.passive}")
        await proxmox.wait_for_agent(vmid=cluster.state.passive.vmid)
        command = await client.generate_config_command(id=self.payload.id, node_type="passive")
        status = await proxmox.agent_execute_script(vmid=cluster.state.passive.vmid, script=command)
        if status.exitcode > 0:
            return await self.fail(f"Passive Node configuration failed: {status.stderr}")

        await DNSClient().add_sector_a_records(
            cluster.config.sector,
            cluster.config.id,
            ARecord(address=cluster.config.vip.ip),
        )
        await self.succeed(f"DockFS {self.payload.id} created.")

    async def on_succeed(self) -> None:
        """Success."""
        await DockFSClient().set_cluster_status(id=self.payload.id, status=DockFSStatus.AVAILABLE)
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("dockfs_clusters")])


class DeleteDockFsV1(Workflow):
    """DockFS Delete Workflow V1."""

    TYPE: str = "dockfs.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[DockFsPayload] = DockFsPayload
    payload: DockFsPayload

    async def validate(self) -> None:
        """Validate that hosts are configured and delete if not."""
        client = DockFSClient()
        
        if not await client.cluster_exists(id=self.payload.id):
            return await self.fail(f"DockFS {self.payload.id} does not exist")

        await client.set_cluster_status(id=self.payload.id, status=DockFSStatus.DELETING)
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("dockfs_clusters")])

    async def provision(self) -> None:
        """Delete the active and passive DockFS nodes."""
        client = DockFSClient()
        proxmox = ProxmoxCompute()
        cluster = await client.get_dockfs(id=self.payload.id)

        await DNSClient().remove_sector_a_records(
            cluster.config.sector,
            cluster.config.id,
            ARecord(address=cluster.config.vip.ip),
        )
        if cluster.state.passive:
            await proxmox.terminate(vmid=cluster.state.passive.vmid)
        if cluster.state.active:
            await proxmox.terminate(vmid=cluster.state.active.vmid)

        await client.delete(id=self.payload.id)
        await self.succeed(f"DockFS {self.payload.id} deleted.")

    async def on_succeed(self) -> None:
        """Success."""
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("dockfs_clusters")])


class RelayedPayload(DockFsPayload):
    """DockFS Workflow payload with network address."""

    address: Annotated[IPv4Interface, SerializeIP]


class ReconcileDockFsV1(Workflow):
    """DockFS Reconcile Workflow V1."""

    TYPE: str = "dockfs.reconcile"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[RelayedPayload] = RelayedPayload
    payload: RelayedPayload

    async def validate(self) -> None:
        """Validate reconciliation request and  proceed if from passive node."""
        client = DockFSClient()
        
        if not await client.cluster_exists(id=self.payload.id):
            return await self.fail(f"DockFS {self.payload.id} does not exist")

        cluster = await client.get_dockfs(id=self.payload.id)
        if cluster.state.active and cluster.state.active.address.ip == self.payload.address.ip:
            await self.succeed(f"Reconciliation is from Active node {cluster.state.active}, ignoring.")

    async def provision(self) -> None:
        """Promote passive node to active and create new passive node."""
        client = DockFSClient()
        proxmox = ProxmoxCompute()
        cluster = await client.get_dockfs(id=self.payload.id)
        
        await self.log(f"Terminating failed active node {cluster.state.active}.")
        await proxmox.terminate(vmid=cluster.state.active.vmid)
        await self.log(f"Setting node {cluster.state.passive} as active.")
        await client.set_node(id=self.payload.id, node=cluster.state.passive, node_type="active")
        
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_node_params(id=self.payload.id, vmid=vmid, node_type="passive")
        await self.log(f"Creating Passive Node {vmid} for {self.payload.id} with params: {self._redact_params(params)}")
        await proxmox.create_vm(params=params)
        await proxmox.start(vmid=vmid)

    async def configure(self) -> RelayedPayload:
        """Configure the new passive DockFS node."""
        client = DockFSClient()
        proxmox = ProxmoxCompute()
        cluster = await client.get_dockfs(id=self.payload.id)
        
        await self.log(f"Configuring {self.payload.id} Passive Node {cluster.state.passive}")
        await proxmox.wait_for_agent(vmid=cluster.state.passive.vmid)
        command = await client.generate_config_command(id=self.payload.id, node_type="passive")
        status = await proxmox.agent_execute_script(vmid=cluster.state.passive.vmid, script=command)
        if status.exitcode > 0:
            return await self.fail(f"Passive Node configuration failed: {status.stderr}")
        
        await self.succeed("Passive node created.")

    async def on_succeed(self) -> None:
        """Success."""
        await DockFSClient().set_cluster_status(id=self.payload.id, status=DockFSStatus.AVAILABLE)
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("dockfs_clusters")])


class FailoverDockFsV1(Workflow):
    """DockFS Failover Workflow V1."""

    TYPE: str = "dockfs.failover"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[RelayedPayload] = RelayedPayload
    payload: RelayedPayload

    async def validate(self) -> None:
        """Validate failover request and proceed if from active node."""
        client = DockFSClient()
        
        if not await client.cluster_exists(id=self.payload.id):
            return await self.fail(f"DockFS {self.payload.id} does not exist")

        cluster = await client.get_dockfs(id=self.payload.id)
        if cluster.state.passive and cluster.state.passive.address.ip == self.payload.address.ip:
            await self.succeed(f"Failover is from Passive node {cluster.state.passive}, ignoring.")

        await client.set_cluster_status(id=self.payload.id, status=DockFSStatus.DEGRADED)
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("dockfs_clusters")])

    async def provision(self) -> None:
        """Perform failover: stop active node and promote passive node."""
        client = DockFSClient()
        proxmox = ProxmoxCompute()
        cluster = await client.get_dockfs(id=self.payload.id)

        await proxmox.stop(vmid=cluster.state.active.vmid)
        await proxmox.move_disk(from_vmid=cluster.state.active.vmid, to_vmid=cluster.state.passive.vmid, disk_id="scsi1")
        status = await proxmox.agent_execute_script(vmid=cluster.state.passive.vmid, script="dockfs promote")
        if status.exitcode > 0:
            return await self.fail(f"Promotion of {cluster.state.passive} to active failed: {status.stderr}")
        
        await self.succeed(f"Successfully promoted {cluster.state.passive} to active")

    async def on_succeed(self) -> None:
        """Success."""
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("dockfs_clusters")])

    async def on_failure(self) -> None:
        """Failure."""
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("dockfs_clusters")])
