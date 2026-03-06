"""DataCore Workflows."""

import asyncio
from ipaddress import IPv4Interface
from typing import Annotated

from orbitlab.data_types import DataCoreStatus, DataCoreEvent, DataCoreNodeRole, ETCDStatus
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.datacore import DataCoreManifest
from orbitlab.manifest.serialization import SerializeIP
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.pages.datacore.states import DataCoreServiceState
from orbitlab.worker.workflows.utilities import DataCoreUtils

from .base import Workflow, WorkflowPayload

ETCD_SERVICE_NAME = "ol:service:datacore-etcd"

class EtcdPayload(WorkflowPayload):
    """Default ETCD Payload."""

    redis_name: str = "ol:datacore:etcd:cluster"


class CreateETCDClusterV1(Workflow, DataCoreUtils):
    """Workflow for creating an ETCD cluster."""

    TYPE: str = "datacore.etcd.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[EtcdPayload] = EtcdPayload
    IDP_TOKEN: str = ETCD_SERVICE_NAME
    payload: EtcdPayload

    async def validate(self) -> None:
        """Validate ETCD cluster configuration."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        if cluster_manifest.spec.etcd is not None:
            await self.succeed("ETCD cluster already created")
            return
        await self.set_redis_hash_value(name=self.payload.redis_name, key="status", value=ETCDStatus.PENDING)
        await self.emit_reflex_events(events=[DataCoreServiceState.cache_clear("etcd_cluster_status")])

    async def provision(self) -> None:
        """Provision ETCD cluster members."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))

        vmids = await self.get_available_vmids(count=4)
        addresses = cluster_manifest.get_next_available_ip(count=4)
        names = [cluster_manifest.generate_etcd_member_name() for _ in range(4)]

        etcd = cluster_manifest.generate_empty_etcd()
        members = await asyncio.gather(
            *(
                self.create_etcd_member(vmid=vmid, name=name, address=address, cluster_manifest=cluster_manifest)
                for vmid, name, address in zip(vmids, names, addresses, strict=False)
            ),
        )
        etcd.members = members
        cluster_manifest.spec.etcd = etcd
        cluster_manifest.save()

    async def configure(self) -> None:
        """Configure ETCD cluster discovery records."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        for member in cluster_manifest.spec.etcd.members:
            await self.create_etcd_discovery_records(name=member.name, address=member.address)
        await self.restart_dns()

    async def finalize(self) -> None:
        """Start all ETCD cluster members."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        await asyncio.gather(*(self.start(vmid=member.vmid) for member in cluster_manifest.spec.etcd.members))

    async def on_succeed(self) -> None:
        await self.set_redis_hash_value(name=self.payload.redis_name, key="status", value=ETCDStatus.AVAILABLE)
        await self.emit_reflex_events(events=[DataCoreServiceState.cache_clear("etcd_cluster_status")])
        await self.emit_reflex_events(events=[ClusterDefaults.cache_clear("_cluster")])
    
    async def on_failure(self) -> None:
        await self._create_new_workflow(
            workflow=DeleteETCDClusterV1,
            payload=DeleteETCDClusterV1.PAYLOAD_TYPE.model_validate({}),
        )


class FailoverPayload(EtcdPayload):
    """Payload for ETCD member failover."""

    name: str
    address: Annotated[IPv4Interface, SerializeIP]


class ETCDMemberFailoverV1(Workflow, DataCoreUtils):
    """Workflow for creating an ETCD cluster."""

    TYPE: str = "datacore.etcd.failover"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[FailoverPayload] = FailoverPayload
    IDP_TOKEN: str = ETCD_SERVICE_NAME
    payload: FailoverPayload

    async def validate(self) -> None:
        """Validate ETCD cluster exists for failover."""
        manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        if manifest.spec.etcd is None:
            await self.fail("No ETCD Cluster configured.")
        await self.set_redis_hash_value(name=self.payload.redis_name, key="status", value=ETCDStatus.DEGRADED)
        await self.emit_reflex_events(events=[DataCoreServiceState.cache_clear("etcd_cluster_status")])

    async def provision(self) -> None:
        """Provision replacement ETCD member."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        vmid = self.proxmox.get_next_vmid()
        address = cluster_manifest.get_next_available_ip()
        name = cluster_manifest.generate_etcd_member_name()
        await self.create_etcd_discovery_records(name=name, address=address)
        new_member = await self.create_etcd_member(
            vmid=vmid, name=name, address=address, cluster_manifest=cluster_manifest,
        )
        # When new members are created, they automatically add themselves to the cluster
        cluster_manifest.spec.etcd.members.append(new_member)
        cluster_manifest.save()

    async def configure(self) -> None:
        """Remove failing ETCD member from cluster."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        failing_member = cluster_manifest.spec.etcd.get_member(member_name=self.payload.name)
        if not failing_member:
            await self.succeed(f"ETCD member {failing_member} does not exist or already deleted.")
            return

        active_member = cluster_manifest.spec.etcd.get_active_member(failing_member=failing_member.name)
        await asyncio.gather(
            self.remove_etcd_member(vmid=active_member.vmid, name=failing_member.name),
            self.delete_etcd_member(
                vmid=failing_member.vmid,
                name=failing_member.name,
                address=failing_member.address,
                cluster_manifest=cluster_manifest,
            ),
        )

        cluster_manifest.spec.etcd.members.remove(failing_member)
        cluster_manifest.save()

    async def on_succeed(self) -> None:
        await self.set_redis_hash_value(name=self.payload.redis_name, key="status", value=ETCDStatus.AVAILABLE)
        await self.emit_reflex_events(events=[DataCoreServiceState.cache_clear("etcd_cluster_status")])


class DeleteETCDClusterV1(Workflow, DataCoreUtils):
    """Workflow for deleting an ETCD cluster."""

    TYPE: str = "datacore.etcd.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[EtcdPayload] = EtcdPayload
    IDP_TOKEN: str = ETCD_SERVICE_NAME
    payload: EtcdPayload

    async def validate(self) -> None:
        """Validate ETCD cluster exists for deletion."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        if cluster_manifest.spec.etcd is None:
            await self.succeed("ETCD cluster doesn't exist")
            return
        await self.set_redis_hash_value(name=self.payload.redis_name, key="status", value=ETCDStatus.DELETING)
        await self.emit_reflex_events(events=[DataCoreServiceState.cache_clear("etcd_cluster_status")])

    async def provision(self) -> None:
        """Delete ETCD cluster members."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        await asyncio.gather(
            *(
                self.delete_etcd_member(
                    vmid=member.vmid, name=member.name, address=member.address, cluster_manifest=cluster_manifest,
                )
                for member in cluster_manifest.spec.etcd.members
            ),
        )
        cluster_manifest.spec.etcd = None
        cluster_manifest.save()

    async def configure(self) -> None:
        """Clean up ETCD cluster configuration."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        cluster_manifest.spec.etcd = None
        cluster_manifest.save()

    async def on_succeed(self) -> None:
        await self.set_redis_hash_value(name=self.payload.redis_name, key="status", value=ETCDStatus.ABSENT)
        await self.emit_reflex_events(events=[DataCoreServiceState.cache_clear("etcd_cluster_status")])
        await self.emit_reflex_events(events=[ClusterDefaults.cache_clear("_cluster")])


class DataCorePayload(WorkflowPayload):
    """Payload for DataCore cluster creation."""

    manifest: str
    
    @property
    def redis_name(self) -> str:
        """DataCore Workflow Redis Key."""
        return f"ol:datacore:{self.manifest}"


class CreateDataCoreCluster(Workflow, DataCoreUtils):
    """Workflow for creating a DataCore cluster."""

    TYPE: str = "datacore.cluster.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[DataCorePayload] = DataCorePayload
    payload: DataCorePayload

    async def validate(self) -> None:
        """Validate DataCore cluster manifest exists."""
        if self.payload.manifest not in DataCoreManifest.get_existing():
            await self.fail(f"DataCore cluster {self.payload.manifest} doesn't exist")
        await self.set_redis_hash_value(name=self.payload.redis_name, key="state", value=DataCoreStatus.PENDING)
        await self.emit_reflex_events(events=[DataCoreServiceState.cache_clear("clusters")])

    async def provision(self) -> None:
        """Provision DataCore cluster nodes and configuration."""
        manifest = DataCoreManifest.load(name=self.payload.manifest)
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))

        await self.create_datacore_config(name=manifest.name, config=manifest.generate_cluster_config())

        vmid = self.proxmox.get_next_vmid()
        await self.create_datacore_node(
            params=manifest.generate_node_params(
                vmid=vmid,
                volume_id=cluster_manifest.metadata.datacore_appliance.volume_id,
            ),
        )

        for i in range(manifest.spec.replicas):
            await self.log(f"Creating DataCore replica {i + 1}")
            vmid = self.proxmox.get_next_vmid()
            await self.create_datacore_node(
                params=manifest.generate_node_params(
                    vmid=vmid,
                    volume_id=cluster_manifest.metadata.datacore_appliance.volume_id,
                ),
            )

    async def configure(self) -> None:
        """Configure DataCore cluster sector records."""
        manifest = DataCoreManifest.load(name=self.payload.manifest)
        await self.create_datacore_sector_record(
            sector=manifest.spec.sector, address=manifest.spec.rw_vip, name=manifest.name,
        )
        await self.create_datacore_sector_record(
            sector=manifest.spec.sector, address=manifest.spec.ro_vip, name=f"{manifest.name}-ro",
        )
        await self.succeed(f"Created DataCore {manifest.name}")

    async def on_succeed(self) -> None:
        return await self.emit_reflex_events(events=[DataCoreServiceState.cache_clear("clusters")])

    async def on_failure(self) -> None:
        """Clean up DataCore cluster on creation failure."""
        await self._create_new_workflow(
            workflow=DeleteDataCoreCluster,
            payload=DeleteDataCoreCluster.PAYLOAD_TYPE.model_validate({"manifest": self.payload.manifest}),
        )


class DeleteDataCoreCluster(Workflow, DataCoreUtils):
    """Workflow for deleting a DataCore cluster."""

    TYPE: str = "datacore.cluster.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[DataCorePayload] = DataCorePayload
    payload: DataCorePayload

    async def validate(self) -> None:
        """Validate DataCore cluster manifest exists."""
        if self.payload.manifest not in DataCoreManifest.get_existing():
            await self.fail(f"DataCore cluster {self.payload.manifest} doesn't exist")
            return
        await self.set_redis_hash_value(name=self.payload.redis_name, key="state", value=DataCoreStatus.DELETING)
        await self.emit_reflex_events(events=[DataCoreServiceState.cache_clear("clusters")])

    async def provision(self) -> None:
        """Delete DataCore cluster nodes and configuration."""
        manifest = DataCoreManifest.load(name=self.payload.manifest)

        await self.log(f"Deleting {manifest.name} config and nodes")
        await asyncio.gather(
            self.delete_datacore_config(name=manifest.name),
            *[self.terminate(vmid=node.vmid) for node in manifest.metadata.nodes],
        )

    async def configure(self) -> None:
        """Delete DataCore cluster DNS VIP records."""
        manifest = DataCoreManifest.load(name=self.payload.manifest)

        await self.log(f"Deleting {manifest.name} writer DNS VIP record in sector {manifest.spec.sector}")
        await self.delete_datacore_sector_record(
            sector=manifest.spec.sector, virtual_router_id=manifest.spec.rw_virtual_router_id,
        )
        await self.log(f"Deleting {manifest.name} reader DNS VIP record in sector {manifest.spec.sector}")
        await self.delete_datacore_sector_record(
            sector=manifest.spec.sector, virtual_router_id=manifest.spec.ro_virtual_router_id,
        )
        manifest.delete()
        await self.succeed(f"Deleted DataCore {self.payload.manifest}")

    async def on_succeed(self) -> None:
        """Emit cache clear event on successful cluster deletion."""
        return await self.emit_reflex_events(events=[DataCoreServiceState.cache_clear("clusters")])


class DataCoreEventPayload(DataCorePayload):
    """Payload for DataCore cluster Patroni events."""

    node: str
    role: DataCoreNodeRole
    event: DataCoreEvent


class DataCoreClusterEvent(Workflow, DataCoreUtils):
    TYPE: str = "datacore.cluster.event"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[DataCoreEventPayload] = DataCoreEventPayload
    payload: DataCoreEventPayload

    async def validate(self) -> None:
        current_status = await self.get_redis_hash_value(name=self.payload.redis_name, key="state", value_type=DataCoreStatus)
        await self.log(f"Current {self.payload.manifest} status: {current_status}")

        if self.payload.role == DataCoreNodeRole.PRIMARY:
            # Handle Primary Node events
            if current_status == DataCoreStatus.PENDING and self.payload.event == DataCoreEvent.ON_START:
                await self.set_redis_hash_value(name=self.payload.redis_name, key="state", value=DataCoreStatus.DEGRADED)
                await self.emit_reflex_events(events=[DataCoreServiceState.cache_clear("clusters")])
                await self.succeed(f"Primary node for {self.payload.manifest} online.")
            else:
                print(self.payload)
                await self.fail(f"{current_status}")

        else:
            # Handle replica node events
            if current_status == DataCoreStatus.DEGRADED and self.payload.event == DataCoreEvent.ON_START:
                await self.set_redis_hash_value(name=self.payload.redis_name, key="state", value=DataCoreStatus.AVAILABLE)
                await self.emit_reflex_events(events=[DataCoreServiceState.cache_clear("clusters")])
                await self.succeed(f"Replica node for {self.payload.manifest} online.")
            else:
                print(self.payload)
                await self.fail(f"{current_status}")
