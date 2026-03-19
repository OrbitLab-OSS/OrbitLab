"""Sector Workflows."""

from orbitlab.data_types import SectorState, StorageContentType
from orbitlab.manifest.sector import SectorManifest
from orbitlab.web.pages.sectors.dashboard.states import SectorsTableState
from orbitlab.worker.workflows.utilities import LXCUtils, SectorUtils

from .base import Workflow, WorkflowPayload


class SectorPayload(WorkflowPayload):
    """Create Network Sector Payload."""

    manifest: str

    @property
    def redis_name(self) -> str:
        """Redis Key."""
        return f"ol:sector:{self.manifest}"


class CreateSectorV1(Workflow, SectorUtils, LXCUtils):
    """Create Network Sector."""

    TYPE: str = "sector.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[SectorPayload] = SectorPayload
    payload: SectorPayload

    async def validate(self) -> None:
        """Validate the sector gateway, if VMID already assigned proceed to finalize."""
        if self.payload.manifest not in SectorManifest.get_existing():
            await self.fail(f"Sector manifest {self.payload.manifest} does not exist")
            return

        await self.redis.hset(name=self.payload.redis_name, key="state", value=SectorState.PENDING.value) # pyright: ignore[reportGeneralTypeIssues]
        await self.emit_reflex_events(events=[SectorsTableState.cache_clear("sectors")])

        manifest = SectorManifest.load(name=self.payload.manifest)
        if manifest.metadata.gateway_vmid:
            await self.succeed(f"Sector {self.payload.manifest} already created and configured.")

    async def provision(self) -> None:
        """Provision the new sector."""
        manifest = SectorManifest.load(name=self.payload.manifest)
        await self.log(f"Creating Sector {self.payload.manifest} with cidr {manifest.spec.cidr_block}.")
        await self.run_sync(self.proxmox_networks.create_sector, manifest=manifest)

    async def configure(self) -> None:
        """Create and configure the sector gateway appliance."""
        manifest = SectorManifest.load(name=self.payload.manifest)
        vmid = self.proxmox_networks.get_next_vmid()
        storage = next(iter(self.proxmox_networks.list_storages_for_node(
            node=self.proxmox_networks.__node__, content_type=StorageContentType.ROOTDIR),
        ))
        params = manifest.generate_gateway_params(vmid=vmid, storage=storage)
        await self.log(f"Creating Sector gateway {vmid} with params: {self._redact_params(params=params)}.")
        await self.create_gateway(params=params)
        await self.start(vmid=vmid)

    async def on_succeed(self) -> None:
        """Mark sector as available."""
        await self.redis.hset(name=self.payload.redis_name, key="state", value=SectorState.AVAILABLE.value) # pyright: ignore[reportGeneralTypeIssues]
        await self.emit_reflex_events(events=[SectorsTableState.cache_clear("sectors")])

    async def on_failure(self) -> None:
        """Queue the sector for deletion."""
        await self._create_new_workflow(
            workflow=DeleteSectorV1,
            payload=DeleteSectorV1.PAYLOAD_TYPE.model_validate({"manifest": self.payload.manifest}),
        )


class DeleteSectorV1(Workflow, SectorUtils):
    """Delete a Sector."""

    TYPE: str = "sector.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[SectorPayload] = SectorPayload
    payload: SectorPayload

    async def validate(self) -> None:
        """Validate the sector exists."""
        if self.payload.manifest not in SectorManifest.get_existing():
            await self.succeed(f"Sector {self.payload.manifest} doesn't exist or already deleted.")
            return

        manifest = SectorManifest.load(name=self.payload.manifest)
        if not await self.sector_exists(tag=manifest.spec.tag):
            manifest.delete()
            await self.succeed(f"Sector {self.payload.manifest} doesn't exist in Proxmox.")
        else:
            await self.redis.hset(name=self.payload.redis_name, key="state", value=SectorState.DELETING.value) # pyright: ignore[reportGeneralTypeIssues]
            await self.emit_reflex_events(events=[SectorsTableState.cache_clear("sectors")])

    async def provision(self) -> None:
        """Delete the sector and appliance."""
        manifest = SectorManifest.load(name=self.payload.manifest)
        await self.log(f"Deleting sector {self.payload.manifest}")
        await self.run_sync(self.proxmox_networks.delete_sector, manifest=manifest)
        manifest.delete()
        await self.succeed(f"Sector {self.payload.manifest} deleted.")

    async def on_succeed(self) -> None:
        """Delete the state from Redis."""
        await self.redis.hdel(self.payload.redis_name, "state")
        await self.emit_reflex_events(events=[SectorsTableState.cache_clear("sectors")])

    async def on_failure(self) -> None:
        """Actions to perform on workflow failure."""
        await self.emit_reflex_events(events=[SectorsTableState.cache_clear("sectors")])
