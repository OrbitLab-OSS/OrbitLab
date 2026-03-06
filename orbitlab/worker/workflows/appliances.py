"""Appliance (CT Template) Workflows."""

from datetime import UTC, datetime
from typing import Literal

import reflex as rx

from orbitlab.data_types import WorkflowStatus
from orbitlab.manifest.compute_templates import BaseApplianceManifest, CustomApplianceManifest, FileStep, ScriptStep
from orbitlab.web.pages.compute.lxc.appliances.states import (
    BaseApplianceTableState,
    CustomApplianceTableState,
)
from orbitlab.worker.workflows.utilities import LXCApplianceUtils, LXCUtils

from .base import Workflow, WorkflowPayload


class AppliancePayload(WorkflowPayload):
    """Payload for appliance workflows."""

    manifest: str

    @property
    def redis_name(self) -> str:
        """Custom Appliance Redis Key."""
        return f"ol:appliance:{self.manifest}"


class ApplianceDownloadPayload(AppliancePayload):
    """Payload for downloading base appliances."""

    update: bool = False


class ApplianceDownloadV1(Workflow, LXCApplianceUtils):
    """Workflow for changing the state of an LXC container."""

    TYPE: str = "appliance.download"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ApplianceDownloadPayload] = ApplianceDownloadPayload
    payload: ApplianceDownloadPayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        if self.payload.manifest not in BaseApplianceManifest.get_existing():
            await self.fail(f"Manifest for {self.payload.manifest} does not exist")
        else:
            manifest = BaseApplianceManifest.load(name=self.payload.manifest)
            appliances = self.proxmox_compute_templates.list_stored_appliances(
                node=manifest.spec.node,
                storage=manifest.spec.storage,
            )
            if appliances.template_exists(template=manifest.spec.template) and not self.payload.update:
                await self.succeed(f"Template {manifest.spec.template} and update not requested.")

    async def provision(self) -> None:
        """Download the appliance."""
        manifest = BaseApplianceManifest.load(name=self.payload.manifest)
        await self.download(node=manifest.spec.node, storage=manifest.spec.storage, template=manifest.spec.template)
        manifest.spec.volume_id = await self.get_volume_id(
            node=manifest.spec.node, storage=manifest.spec.storage, filename=manifest.spec.template,
        )
        manifest.metadata.download_date = datetime.now(tz=UTC)
        manifest.save()

    async def on_succeed(self) -> None:
        """Emit reflex events to notify of success."""
        manifest = BaseApplianceManifest.load(name=self.payload.manifest)
        message = f"Download of {manifest.spec.template} complete."
        if self.payload.update:
            message = f"Update of {manifest.spec.template} complete."
        await self.emit_reflex_events(
            events=[
                BaseApplianceTableState.cache_clear("base_appliances"),
                rx.toast.success(message=message),
            ],
        )

    async def on_failure(self) -> None:
        """Delete manifest if it exists and we're not updating."""
        if self.payload.manifest in BaseApplianceManifest.get_existing() and not self.payload.update:
            BaseApplianceManifest.load(name=self.payload.manifest).delete()


class ApplianceDeletePayload(AppliancePayload):
    """Payload for deleting appliances."""

    appliance_type: Literal["custom", "base"]


class ApplianceDeleteV1(Workflow, LXCApplianceUtils):
    """Workflow for changing the state of an LXC container."""

    TYPE: str = "appliance.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ApplianceDeletePayload] = ApplianceDeletePayload
    payload: ApplianceDeletePayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        if self.payload.appliance_type == "base" and self.payload.manifest not in BaseApplianceManifest.get_existing():
            await self.succeed(f"Base appliance {self.payload.manifest} doesn't exist or already deleted.")
            return
        if (
            self.payload.appliance_type == "custom"
            and self.payload.manifest not in CustomApplianceManifest.get_existing()
        ):
            await self.succeed(f"Custom appliance {self.payload.manifest} doesn't exist or already deleted.")
            return

        if self.payload.appliance_type == "base":
            manifest = BaseApplianceManifest.load(name=self.payload.manifest)
        else:
            manifest = CustomApplianceManifest.load(name=self.payload.manifest)

        appliances = self.proxmox_compute_templates.list_stored_appliances(
            node=manifest.spec.node,
            storage=manifest.spec.storage,
        )
        template = manifest.spec.template if isinstance(manifest, BaseApplianceManifest) else manifest.name
        if not appliances.template_exists(template=template):
            await self.log(f"Template {template} does not exist in storage. Deleting manifest {manifest.name}.")
            manifest.delete()
            await self.succeed(
                f"{self.payload.appliance_type.capitalize()} appliance {self.payload.manifest} deleted.",
            )

    async def provision(self) -> None:
        """Download the appliance."""
        if self.payload.appliance_type == "base":
            manifest = BaseApplianceManifest.load(name=self.payload.manifest)
        else:
            manifest = CustomApplianceManifest.load(name=self.payload.manifest)

        await self.delete(node=manifest.spec.node, storage=manifest.spec.storage, volume_id=manifest.spec.volume_id)
        if self.payload.appliance_type == "custom":
            await self.log(f"Deleting redis logs and status data for {manifest.name}.")
            await self.redis.hdel(self.payload.redis_name, "logs", "status")

        manifest.delete()
        await self.succeed(f"Deleted manifest {manifest.name}.")

    async def on_succeed(self) -> None:
        """Emit reflex events to notify of success."""
        if self.payload.appliance_type == "base":
            await self.emit_reflex_events(events=[BaseApplianceTableState.cache_clear("base_appliances")])
        else:
            await self.emit_reflex_events(events=[CustomApplianceTableState.cache_clear("custom_appliances")])


class CustomAppliancePayload(AppliancePayload):
    """Payload for LXC workflows."""

    vmid: int = 0


class CreateCustomApplianceV1(Workflow, LXCApplianceUtils, LXCUtils):
    """Create a custom LXC Appliance."""

    TYPE: str = "appliance.custom"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[CustomAppliancePayload] = CustomAppliancePayload
    payload: CustomAppliancePayload

    async def validate(self) -> None:
        """Validate manifest exists and initialize Redis status and logs."""
        if self.payload.manifest not in CustomApplianceManifest.get_existing():
            await self.fail(f"Manifest for {self.payload.manifest} does not exist")
            return
        await self.redis.hset(name=self.payload.redis_name, key="status", value=WorkflowStatus.STARTING.value)
        await self.redis.hset(name=self.payload.redis_name, key="logs", value="")
        await self.emit_reflex_events(events=[CustomApplianceTableState.cache_clear("custom_appliances")])

    async def provision(self) -> None:
        """Provision the LXC compute instance and ensure it's online."""
        manifest = CustomApplianceManifest.load(name=self.payload.manifest)
        self.payload.vmid = self.proxmox_compute_templates.get_next_vmid()
        await self.__update_logs__(redis_name=self.payload.redis_name, lines=[f"Creating VMID {self.payload.vmid}"])
        await self.create(params=manifest.workflow_params(vmid=self.payload.vmid), node=manifest.spec.node)
        await self.start(vmid=self.payload.vmid)

    async def configure(self) -> None:
        """Run custom appliance configuration steps, then stop the instance."""
        manifest = CustomApplianceManifest.load(name=self.payload.manifest)

        await self.redis.hset(name=self.payload.redis_name, key="status", value=WorkflowStatus.RUNNING.value)
        await self.emit_reflex_events(events=[CustomApplianceTableState.cache_clear("custom_appliances")])

        conn = self.proxmox_compute_templates.create_connection(node=manifest.spec.node)
        for step in manifest.spec.steps:
            await self.log(message=f"Running step {step.name}")
            await self.__update_logs__(redis_name=self.payload.redis_name, lines=[f"Executing Step: {step.name}"])
            if isinstance(step, FileStep):
                for file in step.files:
                    await self.__update_logs__(
                        redis_name=self.payload.redis_name,
                        lines=[f"Pushing File: {file.source} to {file.destination}"],
                    )
                    await self.log(message=f"Pushing source {file.source} to {file.destination} on {self.payload.vmid}")
                    conn.lxc_push_file(vmid=self.payload.vmid, source=file.source, destination=file.destination)
            elif isinstance(step, ScriptStep):
                await self.log(message=f"Running script {step.name} on {self.payload.vmid}")
                lines = conn.lxc_execute_script(vmid=self.payload.vmid, content=step.script)
                await self.__update_logs__(redis_name=self.payload.redis_name, lines=lines)

        if not manifest.spec.steps:
            await self.__update_logs__(redis_name=self.payload.redis_name, lines=["No steps to execute"])

        await self.__update_logs__(
            redis_name=self.payload.redis_name, lines=[f"Shutting Down VMID {self.payload.vmid}"],
        )
        await self.stop(vmid=self.payload.vmid, shutdown=True)

    async def finalize(self) -> None:
        """Convert the LXC instance to appliance tarball using vzdump, then terminate the instance."""
        manifest = CustomApplianceManifest.load(name=self.payload.manifest)

        await self.redis.hset(name=self.payload.redis_name, key="status", value=WorkflowStatus.FINALIZING.value)
        await self.emit_reflex_events(events=[CustomApplianceTableState.cache_clear("custom_appliances")])

        await self.__update_logs__(
            redis_name=self.payload.redis_name, lines=[f"Converting LXC {self.payload.vmid} to appliance"],
        )
        await self.generate_appliance(
            vmid=self.payload.vmid,
            node=manifest.spec.node,
            storage=manifest.spec.storage,
            name=manifest.name,
        )
        if not manifest.spec.volume_id:
            manifest.spec.volume_id = await self.get_volume_id(
                node=manifest.spec.node, storage=manifest.spec.storage, filename=manifest.spec.template,
            )
        manifest.metadata.last_execution = datetime.now(UTC)
        manifest.save()

    async def on_succeed(self) -> None:
        """Set the status to SUCCEEDED and cleanup."""
        await self.redis.hset(name=self.payload.redis_name, key="status", value=WorkflowStatus.SUCCEEDED.value)
        await self.__cleanup__()

    async def on_failure(self) -> None:
        """Set the status to FAILED and cleanup."""
        await self.redis.hset(name=self.payload.redis_name, key="status", value=WorkflowStatus.FAILED.value)
        await self.__cleanup__()

    async def __update_logs__(self, redis_name: str, lines: list[str]) -> None:
        """Update the workflow logs in redis."""
        logs = await self.redis.hget(name=redis_name, key="logs")
        if isinstance(logs, bytes):
            logs = logs.decode()

        appended = "\n".join(lines)
        if logs:
            logs += f"\n{appended}"
        else:
            logs = appended

        await self.redis.hset(name=redis_name, key="logs", value=logs)
        await self.emit_reflex_events(events=[CustomApplianceTableState.cache_clear("logs")])

    async def __cleanup__(self) -> None:
        """Cleanup workflow resources and update manifest metadata."""        
        if self.payload.vmid:
            await self.terminate(vmid=self.payload.vmid)
        await self.emit_reflex_events(events=[CustomApplianceTableState.cache_clear("custom_appliances")])
