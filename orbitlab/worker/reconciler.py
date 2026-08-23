"""Flag-only desired-versus-observed validation for managed resources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from redis.asyncio import Redis

from orbitlab.proxmox import Proxmox
from orbitlab.redis.clients import BackplaneClient, DataCoreClient, DockFSClient, ETCDClient, InstanceClient, SectorClient


@dataclass(frozen=True, slots=True)
class ObservedResource:
    """A durable observation made without changing the external resource."""

    resource_id: str
    kind: str
    observed_at: str
    status: Literal["healthy", "drifted", "unreachable"]
    detail: str


class ValidationWorker:
    """Periodically discovers managed resources and raises durable drift flags.

    This worker is deliberately read-only with respect to Proxmox. An operator
    may have changed a resource directly in PVE, so it records the discrepancy
    instead of attempting automatic reconciliation.
    """

    INTERVAL_SECONDS = 60
    OBSERVED_KEY = "ol:observed"
    DRIFT_KEY = "ol:drift"

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._instances = InstanceClient()
        self._backplane = BackplaneClient()
        self._sectors = SectorClient()
        self._datacore = DataCoreClient()
        self._dockfs = DockFSClient()
        self._etcd = ETCDClient()
        for client in (
            self._instances,
            self._backplane,
            self._sectors,
            self._datacore,
            self._dockfs,
            self._etcd,
        ):
            client.__dict__["client"] = redis
        self._proxmox = Proxmox()

    async def run_once(self) -> None:
        """Validate tracked guests without mutating desired state or PVE."""
        for instance in await self._instances.list_instances():
            if not instance.state.vmid:
                continue
            desired_status = str(instance.state.status) if str(instance.state.status) in {"running", "stopped"} else ""
            observation = await self._observe_guest(
                resource_id=instance.config.id,
                kind="instance",
                vmid=instance.state.vmid,
                expected_node=instance.config.node,
                expected_status=desired_status,
            )
            await self._commit(observation)

        await self._observe_managed_services()

    async def _observe_managed_services(self) -> None:
        """Validate infrastructure appliances and clustered service members."""
        try:
            backplane = await self._backplane.get()
            controller_vmid = await self._backplane.get_vmid()
        except Exception:  # Bootstrap may not have created these objects yet.
            backplane = None
            controller_vmid = 0
        if backplane and controller_vmid:
            await self._commit(
                await self._observe_guest(
                    resource_id="controller",
                    kind="backplane",
                    vmid=controller_vmid,
                    expected_status="running",
                )
            )

        for sector in await self._sectors.list_sectors():
            for appliance, vmid in (
                ("gateway", sector.state.gateway_vmid),
                ("conduit", sector.state.conduit_vmid),
                ("wardlink", sector.state.wardlink_vmid),
            ):
                if vmid:
                    await self._commit(
                        await self._observe_guest(
                            resource_id=f"{sector.config.id}:{appliance}",
                            kind="sector-appliance",
                            vmid=vmid,
                            expected_status="running",
                        )
                    )

        for cluster in await self._datacore.list_datacores():
            for member in cluster.state.nodes.root:
                if member.vmid:
                    await self._commit(
                        await self._observe_guest(
                            resource_id=f"{cluster.config.id}:{member.name}",
                            kind="datacore-member",
                            vmid=member.vmid,
                            expected_status="running" if member.online else "",
                        )
                    )

        for cluster in await self._dockfs.list_dockfs_clusters():
            for member in cluster.state.cluster_nodes:
                await self._commit(
                    await self._observe_guest(
                        resource_id=f"{cluster.config.id}:{member.name}",
                        kind="dockfs-member",
                        vmid=member.vmid,
                        expected_status="running",
                    )
                )

        for member in await self._etcd.list_members():
            await self._commit(
                await self._observe_guest(
                    resource_id=member.name,
                    kind="etcd-member",
                    vmid=member.vmid,
                    expected_status="running",
                )
            )

    async def _observe_guest(
        self,
        *,
        resource_id: str,
        kind: str,
        vmid: int,
        expected_node: str = "",
        expected_status: str = "",
    ) -> ObservedResource:
        """Compare one tracked VMID with PVE's observed placement and status."""
        observed_at = datetime.now(UTC).isoformat()
        try:
            guest = await self._proxmox.get_compute_resource(vmid)
        except Exception as error:  # noqa: BLE001
            return ObservedResource(resource_id, kind, observed_at, "unreachable", str(error))
        if expected_node and guest.node != expected_node:
            return ObservedResource(
                resource_id,
                kind,
                observed_at,
                "drifted",
                f"Expected node {expected_node}; Proxmox reports {guest.node}.",
            )
        if expected_status and guest.status != expected_status:
            return ObservedResource(
                resource_id,
                kind,
                observed_at,
                "drifted",
                f"Expected status {expected_status}; Proxmox reports {guest.status}.",
            )
        return ObservedResource(resource_id, kind, observed_at, "healthy", "Observed state matches desired state.")

    async def _commit(self, observation: ObservedResource) -> None:
        """Atomically persist an observation and the associated drift flag."""
        key = f"{observation.kind}:{observation.resource_id}"
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.hset(self.OBSERVED_KEY, key, str(observation))
            if observation.status == "healthy":
                pipeline.hdel(self.DRIFT_KEY, key)
            else:
                pipeline.hset(self.DRIFT_KEY, key, observation.detail)
            await pipeline.execute()
