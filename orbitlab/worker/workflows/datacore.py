"""DataCore Workflows."""

import asyncio
from ipaddress import IPv4Interface
import json
from typing import Annotated

import backoff

from orbitlab.data_types import DataCoreStatus, DataCoreEvent, DataCoreNodeRole, ETCDStatus, SerializeIP
from orbitlab.proxmox import Proxmox
from orbitlab.proxmox.exceptions import PctExecError
from orbitlab.redis.clients import ClusterClient, DNSClient, DataCoreClient, ETCDClient, SectorClient
from orbitlab.redis.models import ARecord
from orbitlab.web.global_state import OrbitLabState

from .base import Workflow, WorkflowPayload


class DataCorePayload(WorkflowPayload):
    """Payload for DataCore cluster creation."""

    id: str


class CreateDataCoreCluster(Workflow):
    """Workflow for creating a DataCore cluster."""

    TYPE: str = "datacore.cluster.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[DataCorePayload] = DataCorePayload
    payload: DataCorePayload

    async def validate(self) -> None:
        """Validate DataCore cluster manifest exists."""
        client = DataCoreClient()
        if not await client.datacore_exists(id=self.payload.id):
            return await self.fail(f"DataCore cluster {self.payload.id} does not exist")
        
        await DataCoreClient().set_cluster_status(id=self.payload.id, status=DataCoreStatus.PENDING)
        await self.emit_reflex_events(OrbitLabState.cache_clear("datacores"))

    async def provision(self) -> None:
        """Provision DataCore cluster nodes and configuration."""
        client = DataCoreClient()
        proxmox = Proxmox()
        dns = DNSClient()
        datacore = await client.get_datacore(id=self.payload.id)

        await asyncio.gather(
            self.log(f"Creating pool {datacore.config.id} with alias {datacore.config.name}"),
            proxmox.create_pool(pool_id=datacore.config.id, alias=datacore.config.name)
        )
        
        await asyncio.gather(
            self.log(f"Creating DataCore {datacore.config.id} sector DNS records."),
            dns.add_sector_a_records(datacore.config.sector, datacore.config.id, ARecord(ip=datacore.config.rw_vip.ip)),
            dns.add_sector_a_records(datacore.config.sector, f"{datacore.config.id}-ro", ARecord(ip=datacore.config.ro_vip.ip)),
        )

        await self.log(f"Creating DataCore {datacore.config.id} Configuration")
        etcd_member = await ETCDClient().get_random_member()
        async with await proxmox.create_connection() as connection:
            config = await client.generate_cluster_config(id=self.payload.id)
            redacted_config = {k: '*****' if 'password' in k else v for k, v in config.items()}
            await self.log(
                f"Using VMID {etcd_member.vmid} to create {datacore.config.id} config {redacted_config}.",
            )
            await connection.lxc_execute_script(vmid=etcd_member.vmid, content=f"etcd-mgr create-datacore {datacore.config.id} '{json.dumps(config)}'")

        vmid = await proxmox.get_next_vmid()
        params = await client.generate_node_params(id=self.payload.id, vmid=vmid)
        await self.log(f"Creating DataCore node VMID {vmid} with params: {self._redact_params(params=params)}.")
        await proxmox.create_instance(instance_type="lxc", params=params)
        await proxmox.start(vmid=vmid)

        for i in range(datacore.config.replicas):
            await self.log(f"Creating DataCore replica {i + 1}")
            vmid = await proxmox.get_next_vmid()
            params = await client.generate_node_params(id=self.payload.id, vmid=vmid)
            await self.log(f"Creating DataCore node VMID {vmid} with params: {self._redact_params(params=params)}.")
            await proxmox.create_instance(instance_type="lxc", params=params)
            await proxmox.start(vmid=vmid)

    async def configure(self) -> None:
        await asyncio.gather(self.log("Starting 60 second cluster warmup..."), asyncio.sleep(60))
        await self._wait_for_node_health()
        await self.succeed(f"Created DataCore {self.payload.id}")

    @backoff.on_predicate(lambda: backoff.fibo(max_value=30), max_time=300, on_backoff=lambda x: print("backoff: ", x), on_giveup=lambda x: print("giveup: ", x))
    async def _wait_for_node_health(self) -> None:
        datacore = await DataCoreClient().get_datacore(id=self.payload.id)
        return datacore.state.nodes.healthy

    async def on_succeed(self) -> None:
        await DataCoreClient().set_cluster_status(id=self.payload.id, status=DataCoreStatus.AVAILABLE)
        await self.emit_reflex_events(OrbitLabState.cache_clear("datacores"))


class DeleteDataCoreCluster(Workflow):
    """Workflow for deleting a DataCore cluster."""

    TYPE: str = "datacore.cluster.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[DataCorePayload] = DataCorePayload
    payload: DataCorePayload

    async def validate(self) -> None:
        """Validate DataCore cluster manifest exists."""
        client = DataCoreClient()
        if not await client.datacore_exists(id=self.payload.id):
            return await self.succeed(f"DataCore cluster {self.payload.id} doesn't exist")
        
        await DataCoreClient().set_cluster_status(id=self.payload.id, status=DataCoreStatus.DELETING)
        await self.emit_reflex_events(OrbitLabState.cache_clear("datacores"))

    async def provision(self) -> None:
        """Delete DataCore cluster nodes and configuration."""
        client = DataCoreClient()
        proxmox = Proxmox()
        dns = DNSClient()
        datacore = await client.get_datacore(id=self.payload.id)

        await self.log(f"Deleting {self.payload.id} config and nodes")
        
        await asyncio.gather(
            self.log(f"Deleting DataCore {datacore.config.id} sector DNS records and stopping nodes."),
            dns.remove_sector_a_records(datacore.config.sector, datacore.config.id, ARecord(ip=datacore.config.rw_vip.ip)),
            dns.remove_sector_a_records(datacore.config.sector, f"{datacore.config.id}-ro", ARecord(ip=datacore.config.ro_vip.ip)),
            *[proxmox.stop(vmid=node.vmid) for node in datacore.state.nodes.root],
        )
        
        await self.log(f"Deleting DataCore {datacore.config.id} Configuration")
        etcd_member = await ETCDClient().get_random_member()
        async with await proxmox.create_connection() as connection:
            await self.log(f"Using VMID {etcd_member.vmid} to delete DataCore {datacore.config.id}.")
            await connection.lxc_execute_script(vmid=etcd_member.vmid, content=f"etcd-mgr delete-datacore {datacore.config.id}")
        
        await self.log(f"Terminating DataCore {datacore.config.id} nodes")
        await asyncio.gather(
            *[proxmox.terminate(vmid=node.vmid) for node in datacore.state.nodes.root],
        )
        
        await self.log(f"Deleting DataCore {datacore.config.id}, VIPs, and pool")
        await asyncio.gather(
            client.delete(id=self.payload.id),
            proxmox.delete_pool(pool_id=self.payload.id),
            SectorClient().release_vips(
                datacore.config.rw_virtual_router_id,
                datacore.config.ro_virtual_router_id,
                id=datacore.config.sector,
            ),
        )
        
        await self.succeed(f"Deleted DataCore {self.payload.id}")

    async def on_succeed(self) -> None:
        """Emit cache clear event on successful cluster deletion."""
        return await self.emit_reflex_events(OrbitLabState.cache_clear("datacores"))


class DataCoreEventPayload(DataCorePayload):
    """Payload for DataCore cluster Patroni events."""

    node: str
    role: DataCoreNodeRole
    event: DataCoreEvent


class DataCoreClusterEvent(Workflow):
    TYPE: str = "datacore.cluster.event"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[DataCoreEventPayload] = DataCoreEventPayload
    payload: DataCoreEventPayload

    async def validate(self) -> None:
        if not await DataCoreClient().datacore_exists(id=self.payload.id):
            return await self.fail(f"DataCore {self.payload.id} does not exist")

    async def provision(self) -> None:
        client = DataCoreClient()
        
        datacore = await client.get_datacore(id=self.payload.id)
        
        if self.payload.event == DataCoreEvent.ON_START:
            datacore.state.nodes.set_node_online(name=self.payload.node, role=self.payload.role)
            await client.update_nodes(id=self.payload.id, nodes=datacore.state.nodes)
            await self.log(
                f"DataCore {self.payload.id} node {self.payload.node} online as {self.payload.role}.",
            )

        if self.payload.event == DataCoreEvent.ON_STOP:
            datacore.state.nodes.set_node_offline(name=self.payload.node, role=self.payload.role)
            await client.update_nodes(id=self.payload.id, nodes=datacore.state.nodes)
            await self.log(
                f"DataCore {self.payload.id} {self.payload.role} node {self.payload.node} offline.",
            )

        else:
            datacore.state.nodes.set_node_role(name=self.payload.node, role=self.payload.role)
            await client.update_nodes(id=self.payload.id, nodes=datacore.state.nodes)
            await self.log(
                f"DataCore {self.payload.id} node {self.payload.node} role changed to {self.payload.role}.",
            )
        
        datacore = await client.get_datacore(id=self.payload.id)
        await self.succeed(f"DataCore {self.payload.id} is {datacore.state.status}", notify=False)

    async def on_succeed(self) -> None:
        await self.emit_reflex_events(OrbitLabState.cache_clear("datacores"))
