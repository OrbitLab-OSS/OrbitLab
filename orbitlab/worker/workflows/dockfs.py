"""DockFS Workflows."""

import asyncio
from ipaddress import IPv4Interface
import json
from typing import Annotated

from orbitlab.data_types import DockFSStatus, SerializeIP
from orbitlab.proxmox import Proxmox
from orbitlab.redis.clients import DNSClient, DockFSClient, ETCDClient, SectorClient
from orbitlab.redis.models import ARecord, DockFSNode
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
        
        await client.set_cluster_status(id=self.payload.id, status=DockFSStatus.PENDING)
        await self.emit_reflex_events(OrbitLabState.cache_clear("dockfs_clusters"))

    async def provision(self) -> None:
        """Provision the active and passive DockFS nodes."""
        client = DockFSClient()
        proxmox = Proxmox()
        
        cluster = await client.get_dockfs(id=self.payload.id)
        
        await asyncio.gather(
            self.log(f"Creating sector {cluster.config.sector} record for VIP {cluster.config.vip}."),
            DNSClient().add_sector_a_records(cluster.config.sector, cluster.config.id, ARecord(ip=cluster.config.vip.ip)),
        )
        
        etcd_member = await ETCDClient().get_random_member()
        async with await proxmox.create_connection() as connection:
            config = await client.generate_cluster_config(id=self.payload.id)
            redacted_config = {k: '*****' if 'password' in k else v for k, v in config.items()}
            await self.log(f"Using VMID {etcd_member.vmid} to create {cluster.config.id} config {redacted_config}.")
            await connection.lxc_execute_script(
                vmid=etcd_member.vmid,
                content=f"etcd-mgr create-dockfs {cluster.config.id} '{json.dumps(config)}'",
            )
        
        for node_type in ("active", "passive"):
            vmid = await proxmox.get_next_vmid()
            mac, params = await client.generate_node_params(id=cluster.config.id, vmid=vmid, node_type=node_type)
            await asyncio.gather(
                self.log(
                    f"Creating {node_type.capitalize()} Node {vmid} for {cluster.config.id} with params: "
                    f" {self._redact_params(params)}"
                ),
                proxmox.create_instance(instance_type="qemu", params=params),
            )
            
            await asyncio.gather(
                self.log(f"Starting {node_type.capitalize()} Node {vmid}"),
                proxmox.start(vmid=vmid),
            )

            await client.set_node(
                id=cluster.config.id,
                node=DockFSNode(name=params["name"], mac=mac, address=None, vmid=vmid),  # We'll start with None and let DHCP fill it later
                node_type=node_type,
            )
        
        await self.succeed(f"DockFS {cluster.config.id} created.")

    async def on_succeed(self) -> None:
        """Success."""
        await DockFSClient().set_cluster_status(id=self.payload.id, status=DockFSStatus.AVAILABLE)
        await self.emit_reflex_events(OrbitLabState.cache_clear("dockfs_clusters"))


class ReconcilePayload(DockFsPayload):
    """DockFS Workflow payload with network address."""

    address: Annotated[IPv4Interface, SerializeIP]


class FailoverDockFsV1(Workflow):
    """DockFS Reconcile Workflow V1."""

    TYPE: str = "dockfs.reconcile"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ReconcilePayload] = ReconcilePayload
    payload: ReconcilePayload

    async def validate(self) -> None:
        """Validate reconciliation request and  proceed if from passive node."""
        client = DockFSClient()
        
        if not await client.cluster_exists(id=self.payload.id):
            return await self.fail(f"DockFS {self.payload.id} does not exist")

        cluster = await client.get_dockfs(id=self.payload.id)
        if cluster.state.passive and cluster.state.passive.address.ip == self.payload.address.ip:
            return await self.succeed(f"Fault is from passive node {cluster.state.active}, ignoring.", notify=False)
        
        proxmox = Proxmox()
        await proxmox.wait_for_agent(vmid=cluster.state.active.vmid)
        status = await proxmox.agent_execute_script(vmid=cluster.state.active.vmid, script="/usr/bin/dockfs-check")
        if status.exitcode == 0:
            return await self.succeed(f"Aassive node {cluster.state.active} healthy.", notify=False)
        
        await DockFSClient().set_cluster_status(id=self.payload.id, status=DockFSStatus.DEGRADED)
        await self.emit_reflex_events(OrbitLabState.cache_clear("dockfs_clusters"))

    async def provision(self) -> None:
        """Promote passive node to active and create new passive node."""
        client = DockFSClient()
        proxmox = Proxmox()
        cluster = await client.get_dockfs(id=self.payload.id)
        
        await proxmox.stop(vmid=cluster.state.active.vmid)
        await asyncio.gather(
            self.log(f"Moving SCSI1 disk from {cluster.state.active} to {cluster.state.passive}"),
            proxmox.move_disk(from_vmid=cluster.state.active.vmid, to_vmid=cluster.state.passive.vmid, disk_id="scsi1"),
        )
        
        await asyncio.gather(
            self.log(f"Promoting {cluster.state.passive} to Active and terminating previous active."),
            client.set_node(id=cluster.config.id, node=cluster.state.passive, node_type="active"),
            self.log(f"Terminating failed active node {cluster.state.active}."),
            proxmox.terminate(vmid=cluster.state.active.vmid),
            client.delete_node(id=cluster.config.id, node=cluster.state.active),
        )

    async def configure(self) -> ReconcilePayload:
        """Configure the new passive DockFS node."""
        client = DockFSClient()
        proxmox = Proxmox()
        
        vmid = await proxmox.get_next_vmid()
        mac, params = await client.generate_node_params(id=self.payload.id, vmid=vmid, node_type="passive")
        await self.log(f"Creating Passive Node {vmid} for {self.payload.id} with params: {self._redact_params(params)}")
        await proxmox.create_instance(instance_type="qemu", params=params)
        await proxmox.start(vmid=vmid)
        address = await proxmox.get_ipv4_address(vmid=vmid)
        if not address:
            return await self.fail(f"Node {vmid} for {self.payload.id} failed to acquire IP")
        await client.set_node(
            id=self.payload.id,
            node=DockFSNode(name=params["name"], mac=mac, address=address, vmid=vmid),
            node_type="passive",
        )
        
        await self.succeed("Passive node created.", notify=False)

    async def on_succeed(self) -> None:
        """Success."""
        await DockFSClient().set_cluster_status(id=self.payload.id, status=DockFSStatus.AVAILABLE)
        await self.emit_reflex_events(OrbitLabState.cache_clear("dockfs_clusters"))


# class FailoverDockFsV1(Workflow):
#     """DockFS Failover Workflow V1."""

#     TYPE: str = "dockfs.failover"
#     SCHEMA: str = "v1"
#     PAYLOAD_TYPE: type[ReconcilePayload] = ReconcilePayload
#     payload: ReconcilePayload

#     async def validate(self) -> None:
#         print(self.payload)
#         print(self.event)


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
        await self.emit_reflex_events(OrbitLabState.cache_clear("dockfs_clusters"))

    async def provision(self) -> None:
        """Delete the active and passive DockFS nodes."""
        client = DockFSClient()
        sectors = SectorClient()
        proxmox = Proxmox()
        cluster = await client.get_dockfs(id=self.payload.id)
        
        vmids = [node.vmid for node in cluster.state.cluster_nodes]
        if vmids:
            await asyncio.gather(
                self.log(f"Stopping {vmids}."),
                *[proxmox.stop(vmid=vmid) for vmid in vmids],
            )
        
        etcd_member = await ETCDClient().get_random_member()
        async with await proxmox.create_connection() as connection:
            await self.log(f"Using VMID {etcd_member.vmid} to delete {self.payload.id} config.")
            await connection.lxc_execute_script(vmid=etcd_member.vmid, content=f"etcd-mgr delete-dockfs {self.payload.id}")
        
        if vmids:
            await asyncio.gather(
                self.log("Terminating instances."),
                *[proxmox.terminate(vmid=vmid) for vmid in vmids],
                *[client.delete_node(id=cluster.config.id, node=node) for node in cluster.state.cluster_nodes],
            )
        
        await asyncio.gather(
            self.log(f"Releasing VIP, removing Sector {cluster.config.sector} VIP DNS record, and deleting cluster."),
            DNSClient().remove_sector_a_records(
                cluster.config.sector, cluster.config.id, ARecord(ip=cluster.config.vip.ip),
            ),
            sectors.release_vips(cluster.config.virtual_router_id, id=cluster.config.sector),
            client.delete(id=self.payload.id),
        )

        await self.succeed(f"DockFS {self.payload.id} deleted.")

    async def on_succeed(self) -> None:
        """Success."""
        await self.emit_reflex_events(OrbitLabState.cache_clear("dockfs_clusters"))
