"""Appliance (CT Template) Workflows."""

import asyncio
import json
from typing import Literal

from orbitlab.data_types import TemplateWorkflowStatus
from orbitlab.proxmox import Proxmox, ProxmoxAdapter
from orbitlab.redis.clients import ApplianceClient, SecretsClient, SectorClient
from orbitlab.redis.models import FileStep, ScriptStep
from .base import Workflow, WorkflowPayload


class AppliancePayload(WorkflowPayload):
    """Payload for appliance workflows."""

    id: str # pyright: ignore[reportGeneralTypeIssues]


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
        if not await client.appliance_exists(appliance_type="base", id=self.payload.id):
            return await self.fail(f"Base Appliance {self.payload.id} does not exist")

    async def provision(self) -> None:
        """Download the appliance."""
        client = ApplianceClient()
        proxmox = Proxmox()
        appliance = await client.get_appliance(appliance_type="base", id=self.payload.id)

        if appliance.config.oci:
            await self.log(f"Pulling {appliance.config.template} to {appliance.config.storage}@{appliance.config.node}")
            volume_id = await proxmox.oci_registry_pull(
                node=appliance.config.node, storage=appliance.config.storage, template=appliance.config.template,
            )
            
        else:
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

        if not await client.appliance_exists(appliance_type=self.payload.appliance_type, id=self.payload.id):
            await self.succeed(f"{self.payload.appliance_type.capitalize()} appliance {self.payload.id} doesn't exist or already deleted.")

    async def provision(self) -> None:
        """Download the appliance."""
        client = ApplianceClient()
        proxmox = Proxmox()
        
        appliance = await client.get_appliance(appliance_type=self.payload.appliance_type, id=self.payload.id)
        await asyncio.gather(
            self.log(f"Deleting {self.payload.appliance_type.capitalize()} appliance: {self.payload.id}"),
            proxmox.delete_appliance(node=appliance.config.node, storage=appliance.config.storage, volume_id=appliance.state.volume_id),
            client.delete_appliance(appliance_type=self.payload.appliance_type, id=self.payload.id),
        )
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
        if not await client.appliance_exists(appliance_type="custom", id=self.payload.id):
            return await self.fail(f"Custom Appliance {self.payload.id} does not exist")
        
        await client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.PENDING)

    async def provision(self) -> None:
        """Provision the LXC compute instance and ensure it's online."""
        client = ApplianceClient()
        proxmox = Proxmox()
        adapter = ProxmoxAdapter(proxmox)
        appliance = await client.get_appliance(appliance_type="custom", id=self.payload.id)
        sector_dns = (await SectorClient().get(id=appliance.config.sector)).config.dns_address.ip

        async def parameters(vmid: int) -> dict:
            params = appliance.config.workflow_create_params(
                vmid=vmid,
                password=SecretsClient.generate_random_password(),
                sector_dns=sector_dns,
            )
            await self.log(f"Creating custom appliance candidate VMID {vmid}@{appliance.config.node} with params: {self._redact_params(params)}")
            return params

        guest = await adapter.create_managed_guest(
            resource_id=f"appliance:{self.payload.id}:builder",
            instance_type="lxc",
            node=appliance.config.node,
            parameters=parameters,
        )
        self.payload.vmid = guest.vmid
        await client.update_workflow_logs(id=self.payload.id, logs=[f"Created VMID {self.payload.vmid}"], reset=True)
        
        await client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.STARTING)
        await asyncio.gather(
            self.log(f"Starting {self.payload.vmid}@{appliance.config.node}"),
            client.update_workflow_logs(id=self.payload.id, logs=[f"Starting {self.payload.vmid}"]),
            proxmox.start(vmid=self.payload.vmid),
        )

    async def configure(self) -> None:
        """Run custom appliance configuration steps, then stop the instance."""
        client = ApplianceClient()
        proxmox = Proxmox()
        appliance = await client.get_appliance(appliance_type="custom", id=self.payload.id)

        await client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.RUNNING)

        async with await proxmox.create_connection() as connection:
            for step in appliance.config.steps:
                await client.update_workflow_logs(id=self.payload.id, logs=[f"Executing Step: {step.name}"])
                
                if isinstance(step, FileStep):
                    for file in step.files:
                        await asyncio.gather(
                            client.update_workflow_logs(id=self.payload.id, logs=[f"Pushing File: {file.source} to {file.destination}"]),
                            self.log(f"Pushing source {file.source} to {file.destination} on {self.payload.vmid}"),
                            connection.lxc_push_file(vmid=self.payload.vmid, source=file.source, destination=file.destination)
                        )
                        
                elif isinstance(step, ScriptStep):
                    content = await self._inject_secrets(step=step)
                    await self.log(f"Running script {step.name} on {self.payload.vmid}")
                    logs = await connection.lxc_execute_script(vmid=self.payload.vmid, content=content)
                    await client.update_workflow_logs(id=self.payload.id, logs=logs)

        if not appliance.config.steps:
            await client.update_workflow_logs(id=self.payload.id, logs=["No steps to execute"])

        await asyncio.gather(
            client.update_workflow_logs(id=self.payload.id, logs=[f"Shutting Down VMID {self.payload.vmid}"]),
            proxmox.shutdown(vmid=self.payload.vmid),
        )

    async def finalize(self) -> None:
        """Convert the LXC instance to appliance tarball using vzdump, then terminate the instance."""
        client = ApplianceClient()
        proxmox = Proxmox()
        appliance = await client.get_appliance(appliance_type="custom", id=self.payload.id)

        await client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.FINALIZING)
        await asyncio.gather(
            client.update_workflow_logs(id=self.payload.id, logs=[f"Converting LXC {self.payload.vmid} to appliance"]),
        )

        volume_id = await proxmox.generate_appliance(
            vmid=self.payload.vmid, appliance_id=self.payload.id, storage=appliance.config.storage,
        )
        await asyncio.gather(
            client.workflow_succeeded(id=self.payload.id, volume_id=volume_id),
            proxmox.terminate(vmid=self.payload.vmid),
        )

    async def on_succeed(self) -> None:
        """Set the status to SUCCEEDED."""
        await ApplianceClient().set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.SUCCEEDED)

    async def on_failure(self) -> None:
        """Set the status to FAILED."""
        await ApplianceClient().set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.FAILED)

    async def _inject_secrets(self, step: ScriptStep) -> str:
        def _resolve_json_value(secret_dict: dict, keys: list[str]) -> str:
            last_key = keys.pop()
            for key in keys:
                secret_dict = secret_dict.get(key, {})
            return secret_dict[last_key]
        
        content = ""
        for match in step.secret_injection_pattern.finditer(step.script):
            secret_name: str = match.group("name")
            version = None
            if _version := match.group("version"):
                version = int(_version)
            secret = await SecretsClient().get(secret_name=secret_name, version=version)
            
            secret_value = secret.secret_string.get_secret_value()
            if pointer := match.group("pointer"):
                secret_dict = json.loads(secret_value)
                keys = [key for key in pointer.split("/") if key]
                secret_value = _resolve_json_value(secret_dict=secret_dict, keys=keys)
                _key = ".".join(keys)
                await self.log(
                    f"Injecting secret '{secret_name}' version '{version if version else 'latest'}' "
                    f"from nested key: '.{_key}'"
                )
            else:
                await self.log(
                    f"Injecting secret '{secret_name}' version '{version if version else 'latest'}'"
                )
            
            placeholder = step.script[match.start():match.end()]
            content = step.script.replace(placeholder, secret_value)

        return content
