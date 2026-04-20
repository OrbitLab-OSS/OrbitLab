"""DataCore Workflows."""

import asyncio
from ipaddress import IPv4Interface
import json
from typing import Annotated

from orbitlab.data_types import DataCoreStatus, DataCoreEvent, DataCoreNodeRole, ETCDStatus, SerializeIP
from orbitlab.proxmox import ProxmoxCompute
from orbitlab.proxmox.exceptions import PctExecError
from orbitlab.redis.clients import ClusterClient, DNSClient, DataCoreClient, ETCDClient
from orbitlab.redis.models import ARecord
from orbitlab.web.global_state import OrbitLabState

from .base import Workflow, WorkflowPayload

ETCD_SERVICE_NAME = "ol:service:datacore-etcd"

class EtcdPayload(WorkflowPayload):
    """Default ETCD Payload."""


class CreateETCDClusterV1(Workflow):
    """Workflow for creating an ETCD cluster."""

    TYPE: str = "datacore.etcd.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[EtcdPayload] = EtcdPayload
    IDP_TOKEN: str = ETCD_SERVICE_NAME
    payload: EtcdPayload

    async def validate(self) -> None:
        """Validate ETCD cluster configuration."""
        if await ETCDClient().is_enabled():
            return await self.succeed("ETCD cluster already created")

    async def provision(self) -> None:
        """Provision ETCD cluster members."""
        client = ETCDClient()
        proxmox = ProxmoxCompute()
        
        await proxmox.create_pool(pool_id="orbitlab-etcd", alias="OrbitLab's ETCD Cluster")
        
        for i in range(3):
            vmid = await proxmox.get_next_vmid()
            params = await client.generate_create_params(vmid=vmid)
            await self.log(f"Creating ETCD #{i + 1} node {vmid} with params: {self._redact_params(params)}")
            await proxmox.create_lxc(params=params)
        
        await client.set_version(version=(await ClusterClient().get_infra_appliances()).version)

    async def configure(self) -> None:
        """Start all ETCD cluster members."""
        proxmox = ProxmoxCompute()
        # Start the cluster and begin the 2 minute warmup
        await asyncio.gather(
            *(proxmox.start(vmid=member.vmid) for member in await ETCDClient().list_members()),
            self.log("Giving cluster a 2 minute warmup before checking health..."),
            asyncio.sleep(120),
        )

    async def finalize(self) -> None:
        """Check the health of all ETCD cluster members."""
        client = ETCDClient()
        proxmox = ProxmoxCompute()
        
        async with await proxmox.create_connection() as connection:
            for member in await client.list_members():
                await self.log(f"Checking health of member {member.name}@{member.vmid}.")
                try:
                    await connection.lxc_execute_script(vmid=member.vmid, content="etcd-mgr health-check")
                except PctExecError as err:
                    await self.log(f"ETCD Member Error: {err}")
                    await self._create_new_workflow(
                        workflow=ETCDMemberFailoverV1,
                        payload=ETCDMemberFailoverV1.PAYLOAD_TYPE.model_validate({"name": member.name, "address": member.address}),
                    )
                else:
                    await self.log(f"Member {member} is healthy.")
        await client.enable()

    async def on_succeed(self) -> None:
        await asyncio.gather(
            ETCDClient().set_status(status=ETCDStatus.AVAILABLE),
            self.emit_reflex_events(events=[OrbitLabState.cache_clear("cluster"), OrbitLabState.cache_clear("etcd_cluster_status")])
        )


class UpgradeETCDClusterV1(Workflow):
    """Workflow for upgrading the ETCD cluster."""

    TYPE: str = "datacore.etcd.upgrade"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[EtcdPayload] = EtcdPayload
    IDP_TOKEN: str = ETCD_SERVICE_NAME
    payload: EtcdPayload

    async def validate(self) -> None:
        """Validate ETCD cluster exists for failover."""
        client = ETCDClient()
        if not await client.is_enabled():
            return await self.fail("No ETCD Cluster configured.")

        if await client.get_version() == (await ClusterClient().get_infra_appliances()).version:
            return await self.succeed("ETCD Cluster already on the latest version.")

        await client.set_status(status=ETCDStatus.UPGRADING)
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("etcd_cluster_status")])

    async def provision(self) -> None:
        """Provision replacement ETCD members."""
        client = ETCDClient()
        proxmox = ProxmoxCompute()
        
        for member in await client.list_members():
            vmid = await proxmox.get_next_vmid()
            params = await client.generate_create_params(vmid=vmid)
            await self.log(f"Creating node {vmid} to replace {member.vmid} with params: {self._redact_params(params)}")
            await proxmox.create_lxc(params=params)
            await proxmox.start(vmid=member.vmid)

            await asyncio.gather(
                proxmox.start(vmid=vmid),
                asyncio.sleep(60),
                self.log(f"Giving new member {vmid} a 1 minute warmup before checking health..."),
            )
            
            async with await proxmox.create_connection() as connection:
                await self.log("Checking health of new member.")
                try:
                    await connection.lxc_execute_script(vmid=vmid, content="etcd-mgr health-check")
                except PctExecError as err:
                    return await self.fail(f"ETCD Member Error: {err}")
                else:
                    await self.log("New member is healthy. Removing old member from cluster.")
                    await connection.lxc_execute_script(vmid=vmid, content=f"etcd-mgr remove-member {member.name}")

            # terminate the old member and delete it
            await asyncio.gather(
                proxmox.terminate(vmid=member.vmid),
                client.remove_member(member=member),
            )

        latest_version = (await ClusterClient().get_infra_appliances()).version
        await client.set_version(version=latest_version)
        await self.succeed(f"Successfully upgraded ETCD cluster to v{latest_version}")

    async def on_succeed(self) -> None:
        await asyncio.gather(
            ETCDClient().set_status(status=ETCDStatus.AVAILABLE),
            self.emit_reflex_events(events=[OrbitLabState.cache_clear("etcd_cluster_status")]),
        )


class FailoverPayload(EtcdPayload):
    """Payload for ETCD member failover."""

    name: str
    address: Annotated[IPv4Interface, SerializeIP]


class ETCDMemberFailoverV1(Workflow):
    """Workflow for creating an ETCD cluster."""

    TYPE: str = "datacore.etcd.failover"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[FailoverPayload] = FailoverPayload
    IDP_TOKEN: str = ETCD_SERVICE_NAME
    payload: FailoverPayload

    async def validate(self) -> None:
        """Validate ETCD cluster exists for failover."""
        await self.fail("STUBBED.")
        # manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        # if manifest.spec.etcd is None:
        #     await self.fail("No ETCD Cluster configured.")
        # await asyncio.gather(
        #     self.set_redis_hash_value(name=self.payload.redis_name, key="status", value=ETCDStatus.DEGRADED),
        #     self.emit_reflex_events(events=[
        #         rx.toast.warning(f"ETCD Cluster member degraded: {self.payload.name}"),
        #         OrbitLabState.cache_clear("etcd_cluster_status"),
        #     ])
        # )

    # async def provision(self) -> None:
    #     """Provision replacement ETCD member."""
    #     cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
    #     member = cluster_manifest.spec.etcd.get_member(member_name=self.payload.name)
        
    #     if await self.member_is_healthy(member=member):
    #         return await self.succeed(f"ETCD member {member.name}@{member.vmid} healthy")
        
    #     vmid = await self.proxmox.get_next_vmid()
    #     address = cluster_manifest.get_next_available_ip()
    #     new_member = cluster_manifest.generate_etcd_member(vmid=vmid, address=address)
        
    #     await asyncio.gather(
    #         self.create_etcd_discovery_records(members=[new_member]),
    #         self.create(params=cluster_manifest.generate_etcd_member_create_params(member=new_member)),
    #     )
        
    #     await asyncio.gather(
    #         self.start(vmid=new_member.vmid),
    #         self.remove_etcd_member(member=member),
    #         self.delete_etcd_member(member=member),
    #     )
    #     # When new members are created, they automatically add themselves to the cluster
    #     cluster_manifest.spec.etcd.members.append(new_member)
    #     if member:
    #         cluster_manifest.spec.etcd.members.remove(member)
    #     cluster_manifest.save()
    #     # Update the payload name so we can check new member health during `finalize()`
    #     self.payload.name = new_member.name

    # async def finalize(self) -> None:   
    #     cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
    #     member = cluster_manifest.spec.etcd.get_member(member_name=self.payload.name)
    #     await asyncio.gather(
    #         asyncio.sleep(60),
    #         self.log(f"Giving new member {member} a 1 minute warmup before checking health..."),
    #     )
    #     if not await self.member_is_healthy(member=member):
    #         await self.log(f"Member {member} is not healthy.")
    #     else:
    #         await self.log(f"Member {member} is healthy.")

    # async def on_succeed(self) -> None:
    #     await asyncio.gather(
    #         self.set_redis_hash_value(name=self.payload.redis_name, key="status", value=ETCDStatus.AVAILABLE),
    #         self.emit_reflex_events(events=[OrbitLabState.cache_clear("etcd_cluster_status")]),
    #     )


class DeleteETCDClusterV1(Workflow):
    """Workflow for deleting an ETCD cluster."""

    TYPE: str = "datacore.etcd.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[EtcdPayload] = EtcdPayload
    IDP_TOKEN: str = ETCD_SERVICE_NAME
    payload: EtcdPayload

    async def validate(self) -> None:
        """Validate ETCD cluster exists for deletion."""
        client = ETCDClient()
        if not await client.list_members():
            return await self.succeed("No ETCD Cluster members.")
        
        await client.set_status(status=ETCDStatus.DELETING)
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("etcd_cluster_status")])

    async def provision(self) -> None:
        """Delete ETCD cluster members."""
        client = ETCDClient()
        proxmox = ProxmoxCompute()
        
        await self.log("Terminating ETCD Cluster members")
        await asyncio.gather(
            proxmox.terminate(vmid=member.vmid) for member in await client.list_members()
        )
        
        await self.log("Removing ETCD Cluster members from infra")
        await asyncio.gather(
            client.remove_member(member=member) for member in await client.list_members()
        )
        
        await self.log("Deleting ETCD Cluster pool and disabling")
        await asyncio.gather(
            proxmox.delete_pool(pool_id="orbitlab-etcd"),
            client.disable()
        )

    async def on_succeed(self) -> None:
        await self.emit_reflex_events(
            events=[OrbitLabState.cache_clear("cluster"), OrbitLabState.cache_clear("etcd_cluster_status")]
        )


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
            return await self.fail(f"DataCore cluster {self.payload.id} doesn't exist")

    async def provision(self) -> None:
        """Provision DataCore cluster nodes and configuration."""
        client = DataCoreClient()
        proxmox = ProxmoxCompute()
        dns = DNSClient()
        datacore = await client.get_datacore(id=self.payload.id)

        await asyncio.gather(
            self.log(f"Creating pool {datacore.config.id} with alias {datacore.config.name}"),
            proxmox.create_pool(pool_id=datacore.config.id, alias=datacore.config.name)
        )
        
        await asyncio.gather(
            self.log(f"Creating DataCore {datacore.config.id} sector DNS records."),
            dns.add_sector_a_records(datacore.config.sector, datacore.config.id, ARecord(address=datacore.config.rw_vip.ip)),
            dns.add_sector_a_records(datacore.config.sector, f"{datacore.config.id}-ro", ARecord(address=datacore.config.ro_vip.ip)),
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
        await proxmox.create_lxc(params=params)
        await proxmox.start(vmid=vmid)

        for i in range(datacore.config.replicas):
            await self.log(f"Creating DataCore replica {i + 1}")
            vmid = await proxmox.get_next_vmid()
            params = await client.generate_node_params(id=self.payload.id, vmid=vmid)
            await self.log(f"Creating DataCore node VMID {vmid} with params: {self._redact_params(params=params)}.")
            await proxmox.create_lxc(params=params)
            await proxmox.start(vmid=vmid)

    async def configure(self) -> None:
        await asyncio.gather(self.log("Starting 30 second cluster warmup..."), asyncio.sleep(30))

    async def finalize(self) -> None:
        """Configure DataCore cluster sector records."""
        client = DataCoreClient()
        proxmox = ProxmoxCompute()
        datacore = await client.get_datacore(id=self.payload.id)
        
        async with await proxmox.create_connection() as connection:
            for node in datacore.state.nodes.root:
                await self.log(f"Checking DataCore Node {node} health.")
                try:
                    await connection.lxc_execute_script(
                        vmid=node.vmid,
                        content="""
                        PATRONICTL="patronictl -c /etc/datacore/patroni.yaml"
                        if ! $PATRONICTL list | grep "$(hostname)" > /dev/null; then
                            echo "DataCore node $(hostname) not in Patroni cluster."
                            exit 1
                        fi
                        if ! su -c "psql -d postgres -Atqc 'SELECT 1;'" - postgres > /dev/null; then
                            echo "Unable to connect to postgres."
                            exit 1
                        fi
                        if [ "$($PATRONICTL list | grep "$(hostname)" | awk '{print $6}')" == "Leader" ]; then
                            if [ "$(su -c "psql -d postgres -Atqc 'SELECT pg_is_in_recovery();'" - postgres)" != "f" ]; then
                                echo "Leader is in recovery but it shouldn't be."
                                exit 1
                            fi
                        else
                            if [ "$($PATRONICTL list | grep "$(hostname)" | awk '{print $8}')" != "streaming" ]; then
                                CLUSTER=$($PATRONICTL list | grep "Cluster" | awk '{print $3}')
                                $PATRONICTL reinit "$CLUSTER" "$(hostname)" --force --wait
                                if [ "$($PATRONICTL list | grep "$(hostname)" | awk '{print $8}')" != "streaming" ]; then
                                    echo "Failed to reinit Replica node $(hostname)."
                                    exit 1
                                fi
                            fi
                        fi
                        """,
                    )
                except Exception as err:
                    print(err)
                    
        await self.succeed(f"Created DataCore {datacore.config.id}")

    async def on_succeed(self) -> None:
        await DataCoreClient().set_cluster_status(id=self.payload.id, status=DataCoreStatus.AVAILABLE)
        return await self.emit_reflex_events(events=[OrbitLabState.cache_clear("datacores")])


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
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("datacores")])

    async def provision(self) -> None:
        """Delete DataCore cluster nodes and configuration."""
        client = DataCoreClient()
        proxmox = ProxmoxCompute()
        dns = DNSClient()
        datacore = await client.get_datacore(id=self.payload.id)

        await self.log(f"Deleting {self.payload.id} config and nodes")
        
        await asyncio.gather(
            self.log(f"Deleting DataCore {datacore.config.id} sector DNS records."),
            dns.remove_sector_a_records(datacore.config.sector, datacore.config.id, ARecord(address=datacore.config.rw_vip.ip)),
            dns.remove_sector_a_records(datacore.config.sector, f"{datacore.config.id}-ro", ARecord(address=datacore.config.ro_vip.ip)),
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
        
        await self.log(f"Deleting DataCore {datacore.config.id} and pool")
        await asyncio.gather(
            client.delete(id=self.payload.id),
            proxmox.delete_pool(pool_id=self.payload.id),
        )
        
        await self.succeed(f"Deleted DataCore {self.payload.id}")

    async def on_succeed(self) -> None:
        """Emit cache clear event on successful cluster deletion."""
        return await self.emit_reflex_events(events=[OrbitLabState.cache_clear("datacores")])


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
        datacore = await DataCoreClient().get_datacore(id=self.payload.id)
        await self.log(f"Current {self.payload.id} status: {datacore.state.status}")

        if self.payload.role == DataCoreNodeRole.PRIMARY:
            # Handle Primary Node events
            if datacore.state.status == DataCoreStatus.PENDING and self.payload.event == DataCoreEvent.ON_START:
                await self.emit_reflex_events(events=[OrbitLabState.cache_clear("datacores")])
                await self.succeed(f"Primary node for {self.payload.id} online.")
            else:
                await self.fail(f"{datacore.state.status}")

        else:
            # Handle replica node events
            if datacore.state.status == DataCoreStatus.DEGRADED and self.payload.event == DataCoreEvent.ON_START:
                await self.emit_reflex_events(events=[OrbitLabState.cache_clear("datacores")])
                await self.succeed(f"Replica node for {self.payload.id} online.")
            else:
                await self.fail(f"{datacore.state.status}")
