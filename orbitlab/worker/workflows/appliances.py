"""Appliance (CT Template) Workflows."""

import asyncio
from typing import Literal

import reflex as rx

from orbitlab.data_types import TemplateWorkflowStatus
from orbitlab.proxmox import ProxmoxCompute, ProxmoxComputeTemplates
from orbitlab.redis.clients import ApplianceClient, SecretsClient, SectorClient
from orbitlab.redis.models import FileStep, ScriptStep
from orbitlab.web.global_state import OrbitLabState

from .base import Workflow, WorkflowPayload


class AppliancePayload(WorkflowPayload):
    """Payload for appliance workflows."""

    id: str


class ApplianceDownloadPayload(AppliancePayload):
    """Payload for downloading base appliances."""

    update: bool = False


class ApplianceDownloadV1(Workflow):
    """Workflow for changing the state of an LXC container."""

    TYPE: str = "appliance.download"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ApplianceDownloadPayload] = ApplianceDownloadPayload
    payload: ApplianceDownloadPayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        client = ApplianceClient()
        if not await client.appliance_exists(id=self.payload.id):
            return await self.fail(f"Base Appliance {self.payload.id} does not exist")

    async def provision(self) -> None:
        """Download the appliance."""
        client = ApplianceClient()
        proxmox = ProxmoxComputeTemplates()
        appliance = await client.get_appliance(id=self.payload.id)
        
        await self.log(f"Downloading {appliance.config.template} to {appliance.config.storage}@{appliance.config.node}")
        volume_id = await proxmox.download_proxmox_managed_appliance(
            node=appliance.config.node, storage=appliance.config.storage, template=appliance.config.template,
        )
        await client.set_appliance_downloaded(id=self.payload.id, volume_id=volume_id)
        await self.succeed(f"Download of {self.payload.id} complete.")


class ApplianceDeletePayload(AppliancePayload):
    """Payload for deleting appliances."""

    appliance_type: Literal["custom", "base"]


class ApplianceDeleteV1(Workflow):
    """Workflow for changing the state of an LXC container."""

    TYPE: str = "appliance.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ApplianceDeletePayload] = ApplianceDeletePayload
    payload: ApplianceDeletePayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        client = ApplianceClient()

        if self.payload.appliance_type == "base" and not await client.appliance_exists(id=self.payload.id):
            return await self.succeed(f"Base appliance {self.payload.id} doesn't exist or already deleted.")
            
        if self.payload.appliance_type == "custom" and not await client.appliance_exists(id=self.payload.id):
            await self.succeed(f"Custom appliance {self.payload.id} doesn't exist or already deleted.")
            return

    async def provision(self) -> None:
        """Download the appliance."""
        client = ApplianceClient()
        proxmox = ProxmoxComputeTemplates()
        
        if self.payload.appliance_type == "base":
            appliance = await client.get_appliance(id=self.payload.id)
            await proxmox.delete_appliance(node=appliance.config.node, storage=appliance.config.storage, volume_id=appliance.state.volume_id)
            await client.delete_appliance(id=self.payload.id)
        else:
            appliance = await client.get_appliance(id=self.payload.id)
            await proxmox.delete_appliance(node=appliance.config.node, storage=appliance.config.storage, volume_id=appliance.state.volume_id)
            await client.delete_appliance(id=self.payload.id)

        await self.succeed(f"Deleted appliance {self.payload.id}.")


class CustomAppliancePayload(AppliancePayload):
    """Payload for LXC workflows."""

    vmid: int = 0


class CreateCustomApplianceV1(Workflow):
    """Create a custom LXC Appliance."""

    TYPE: str = "appliance.custom"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[CustomAppliancePayload] = CustomAppliancePayload
    payload: CustomAppliancePayload

    async def validate(self) -> None:
        """Validate manifest exists and initialize Redis status and logs."""
        client = ApplianceClient()
        if not await client.appliance_exists(id=self.payload.id):
            return await self.fail(f"Custom Image {self.payload.id} does not exist")
        
        await client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.STARTING)

    async def provision(self) -> None:
        """Provision the LXC compute instance and ensure it's online."""
        client = ApplianceClient()
        proxmox = ProxmoxCompute()
        appliance = await client.get_appliance(id=self.payload.id)
        
        self.payload.vmid = await proxmox.get_next_vmid()
        await client.update_workflow_logs(id=self.payload.id, logs=[f"Creating VMID {self.payload.vmid}"], reset=True)
        params = appliance.config.workflow_create_params(
            vmid=self.payload.vmid,
            password=SecretsClient.generate_random_password(),
            sector_dns=(await SectorClient().get(id=appliance.config.sector)).config.dns_address.ip
        )
        
        await asyncio.gather(
            self.log(f"Creating {self.payload.vmid}@{appliance.config.node} with params: {params}"),
            proxmox.create_lxc(params=params, node=appliance.config.node),
        )
        
        await asyncio.gather(
            self.log(f"Starting {self.payload.vmid}@{appliance.config.node}"),
            client.update_workflow_logs(id=self.payload.id, logs=[f"Starting {self.payload.vmid}"]),
            client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.STARTING),
            proxmox.start(vmid=self.payload.vmid),
        )

    async def configure(self) -> None:
        """Run custom appliance configuration steps, then stop the instance."""
        client = ApplianceClient()
        proxmox = ProxmoxCompute()
        appliance = await client.get_appliance(id=self.payload.id)

        await client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.STARTING)

        async with await proxmox.create_connection() as connection:
            for step in appliance.config.steps:
                await client.update_workflow_logs(id=self.payload.id, logs=[f"Executing Step: {step.name}"])
                
                if isinstance(step, FileStep):
                    for file in step.files:
                        await asyncio.gather(
                            client.update_workflow_logs(id=self.payload.id, logs=[f"Pushing File: {file.source} to {file.destination}"]),
                            self.log(message=f"Pushing source {file.source} to {file.destination} on {self.payload.vmid}"),
                            connection.lxc_push_file(vmid=self.payload.vmid, source=file.source, destination=file.destination)
                        )
                        
                elif isinstance(step, ScriptStep):
                    await self.log(message=f"Running script {step.name} on {self.payload.vmid}")
                    logs = await connection.lxc_execute_script(vmid=self.payload.vmid, content=step.script)
                    client.update_workflow_logs(id=self.payload.id, logs=logs),

        if not appliance.config.steps:
            await client.update_workflow_logs(id=self.payload.id, logs=["No steps to execute"])

        await asyncio.gather(
            client.update_workflow_logs(id=self.payload.id, logs=[f"Shutting Down VMID {self.payload.vmid}"]),
            proxmox.shutdown(vmid=self.payload.vmid),
        )

    async def finalize(self) -> None:
        """Convert the LXC instance to appliance tarball using vzdump, then terminate the instance."""
        client = ApplianceClient()
        proxmox = ProxmoxComputeTemplates()
        appliance = await client.get_appliance(id=self.payload.id)

        await asyncio.gather(
            client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.FINALIZING),
            self.emit_reflex_events(events=[OrbitLabState.cache_clear("custom_appliances")]),
            client.update_workflow_logs(id=self.payload.id, logs=[f"Converting LXC {self.payload.vmid} to appliance"]),
        )

        volume_id = await proxmox.generate_appliance(
            vmid=self.payload.vmid, appliance_id=self.payload.id, storage=appliance.config.storage,
        )
        await asyncio.gather(
            client.workflow_succeeded(id=self.payload.id, volume_id=volume_id),
            ProxmoxCompute().terminate(vmid=self.payload.vmid),
        )

    async def on_succeed(self) -> None:
        """Set the status to SUCCEEDED and cleanup."""
        await ApplianceClient().set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.SUCCEEDED)

    async def on_failure(self) -> None:
        """Set the status to FAILED and cleanup."""
        await ApplianceClient().set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.FAILED)
