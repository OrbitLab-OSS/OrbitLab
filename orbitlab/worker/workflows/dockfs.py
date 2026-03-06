"""DockFS Workflows."""

import asyncio
from ipaddress import IPv4Interface
from typing import Annotated

from orbitlab.data_types import DockFSState
from orbitlab.manifest.dockfs import DockFsManifest
from orbitlab.manifest.serialization import SerializeIP
from orbitlab.web.pages.dockfs.states import DockFSTableState

from .base import Workflow, WorkflowPayload
from .utilities import DockFSUtils


class DockFsPayload(WorkflowPayload):
    """DockFS Workflow payload."""

    manifest: str

    @property
    def redis_name(self) -> str:
        """DockFS Workflow Redis Key."""
        return f"ol:dockfs:{self.manifest}"


class CreateDockFsV1(Workflow, DockFSUtils):
    """DockFS Create Workflow V1."""

    TYPE: str = "dockfs.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[DockFsPayload] = DockFsPayload
    payload: DockFsPayload

    async def validate(self) -> None:
        """Validate DockFS Manifest data."""
        if self.payload.manifest not in DockFsManifest.get_existing():
            await self.fail(f"Manifest for {self.payload.manifest} does not exist")
            return
        manifest = DockFsManifest.load(name=self.payload.manifest)
        if manifest.metadata.active and manifest.metadata.passive:
            await self.succeed(f"Hosts for {self.payload.manifest} already configured.")
            return
        if manifest.metadata.active or manifest.metadata.passive:
            await self.fail(f"Hosts for {self.payload.manifest} not configured properly.")
        await self.set_redis_hash_value(name=self.payload.redis_name, key="state", value=DockFSState.PENDING)
        await self.emit_reflex_events(events=[DockFSTableState.cache_clear("clusters")])

    async def provision(self) -> None:
        """Provision the active and passive DockFS nodes."""
        manifest = DockFsManifest.load(name=self.payload.manifest)
        vmids = await self.get_available_vmids(count=2)

        await asyncio.gather(
            self.create_dockfs_node(
                params=manifest.generate_active_params(vmid=vmids[0]),
                dockfs_name=manifest.name,
            ),
            self.create_dockfs_node(
                params=manifest.generate_passive_params(vmid=vmids[1]),
                dockfs_name=manifest.name,
            ),
        )

    async def configure(self) -> None:
        """Configure the active and passive DockFS nodes."""
        manifest = DockFsManifest.load(name=self.payload.manifest)

        if not manifest.metadata.active:
            await self.fail(f"Active host for {manifest.name} not set.")
            return
        if not manifest.metadata.passive:
            await self.fail(f"Passive host for {manifest.name} not set.")
            return

        errors = await asyncio.gather(
            self.configure_dockfs_node(
                dockfs_name=manifest.name,
                node=manifest.metadata.active,
                command=manifest.generate_config_command(config_type="active"),
            ),
            self.configure_dockfs_node(
                dockfs_name=manifest.name,
                node=manifest.metadata.passive,
                command=manifest.generate_config_command(config_type="passive"),
            ),
        )
        for error in errors:
            if error:
                await self.fail(error=error)

        else:
            await self.add_a_record(address=manifest.spec.vip.ip, hostname=manifest.name)
            await self.succeed(f"DockFS {manifest.name} created.")

    async def on_succeed(self) -> None:
        """Success."""
        await self.set_redis_hash_value(name=self.payload.redis_name, key="state", value=DockFSState.AVAILABLE)
        await self.emit_reflex_events(events=[DockFSTableState.cache_clear("clusters")])

    async def on_failure(self) -> None:
        """Failure."""
        await self._create_new_workflow(
            workflow=DeleteDockFsV1,
            payload=DeleteDockFsV1.PAYLOAD_TYPE.model_validate({"manifest": self.payload.manifest}),
        )


class DeleteDockFsV1(Workflow, DockFSUtils):
    """DockFS Delete Workflow V1."""

    TYPE: str = "dockfs.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[DockFsPayload] = DockFsPayload
    payload: DockFsPayload

    async def validate(self) -> None:
        """Validate that hosts are configured and delete if not."""
        if self.payload.manifest not in DockFsManifest.get_existing():
            await self.fail(f"Manifest for {self.payload.manifest} does not exist")
            return

        manifest = DockFsManifest.load(name=self.payload.manifest)
        await self.set_redis_hash_value(name=self.payload.redis_name, key="state", value=DockFSState.DELETING)
        await self.emit_reflex_events(events=[DockFSTableState.cache_clear("clusters")])

        if not manifest.metadata.active and not manifest.metadata.passive:
            manifest.delete()
            await self.succeed(f"No hosts configured for {self.payload.manifest}.")

    async def provision(self) -> None:
        """Delete the active and passive DockFS nodes."""
        manifest = DockFsManifest.load(name=self.payload.manifest)

        await asyncio.gather(
            self.terminate(vmid=manifest.metadata.active.vmid),
            self.terminate(vmid=manifest.metadata.passive.vmid),
            self.delete_a_record(address=manifest.spec.vip.ip),
        )

        manifest.delete()
        await self.succeed(f"DockFS {self.payload.manifest} deleted.")

    async def on_succeed(self) -> None:
        """Success."""
        await self.redis.hdel(self.payload.redis_name, "state")
        await self.emit_reflex_events(events=[DockFSTableState.cache_clear("clusters")])


class RelayedPayload(DockFsPayload):
    """DockFS Workflow payload with network address."""

    address: Annotated[IPv4Interface, SerializeIP]


class ReconcileDockFsV1(Workflow, DockFSUtils):
    """DockFS Reconcile Workflow V1."""

    TYPE: str = "dockfs.reconcile"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[RelayedPayload] = RelayedPayload
    payload: RelayedPayload

    async def validate(self) -> None:
        """Validate reconciliation request and  proceed if from passive node."""
        if self.payload.manifest not in DockFsManifest.get_existing():
            await self.fail(f"Manifest for {self.payload.manifest} does not exist")
            return

        manifest = DockFsManifest.load(name=self.payload.manifest)
        if manifest.metadata.active and manifest.metadata.active.address.ip == self.payload.address.ip:
            await self.succeed(f"Reconciliation is from Active node {manifest.metadata.active}, ignoring.")

    async def provision(self) -> None:
        """Promote passive node to active and create new passive node."""
        manifest = DockFsManifest.load(name=self.payload.manifest)
        await self.log(f"Setting {manifest.metadata.passive} to active.")
        vmid_to_terminate = manifest.failover()
        vmid = self.proxmox_compute.get_next_vmid()

        asyncio.gather(
            await self.terminate(vmid=vmid_to_terminate),
            self.create_dockfs_node(
                params=manifest.generate_passive_params(vmid=vmid),
                dockfs_name=manifest.name,
            ),
        )

    async def configure(self) -> RelayedPayload:
        """Configure the new passive DockFS node."""
        manifest = DockFsManifest.load(name=self.payload.manifest)

        await self.log(f"Configuring new {manifest.name} passive node {manifest.metadata.passive}")
        error = await self.configure_dockfs_node(
            dockfs_name=manifest.name,
            node=manifest.metadata.passive,
            command=manifest.generate_config_command(config_type="passive"),
        )
        if error:
            await self.fail(error=error)
        else:
            await self.succeed("Passive node created.")

    async def on_succeed(self) -> None:
        """Success."""
        await self.set_redis_hash_value(name=self.payload.redis_name, key="state", value=DockFSState.AVAILABLE)
        await self.emit_reflex_events(events=[DockFSTableState.cache_clear("clusters")])


class FailoverDockFsV1(Workflow, DockFSUtils):
    """DockFS Failover Workflow V1."""

    TYPE: str = "dockfs.failover"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[RelayedPayload] = RelayedPayload
    payload: RelayedPayload

    async def validate(self) -> None:
        """Validate failover request and proceed if from active node."""
        if self.payload.manifest not in DockFsManifest.get_existing():
            await self.fail(f"Manifest for {self.payload.manifest} does not exist")
            return

        manifest = DockFsManifest.load(name=self.payload.manifest)
        if manifest.metadata.passive and manifest.metadata.passive.address.ip == self.payload.address.ip:
            await self.succeed(f"Failover is from Passive node {manifest.metadata.active}, ignoring.")

    async def provision(self) -> None:
        """Perform failover: stop active node and promote passive node."""
        manifest = DockFsManifest.load(name=self.payload.manifest)
        if not manifest.metadata.active:
            await self.fail(f"Active node for {self.payload.manifest} not configured.")

        await self.set_redis_hash_value(name=self.payload.redis_name, key="state", value=DockFSState.DEGRADED)
        await self.emit_reflex_events(events=[DockFSTableState.cache_clear("clusters")])

        error = await self.promote(active=manifest.metadata.active, passive=manifest.metadata.passive)
        if error:
            await self.fail(error=error)

    async def on_succeed(self) -> None:
        """Success."""
        await self.emit_reflex_events(events=[DockFSTableState.cache_clear("clusters")])

    async def on_failure(self) -> None:
        """Failure."""
        await self.emit_reflex_events(events=[DockFSTableState.cache_clear("clusters")])
