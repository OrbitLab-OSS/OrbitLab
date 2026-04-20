"""VM Image (QCOW2/RAW) Workflows."""

import asyncio
from typing import Literal

from orbitlab.data_types import TemplateWorkflowStatus
from orbitlab.proxmox import ProxmoxComputeTemplates, ProxmoxCompute
from orbitlab.redis.clients import ImagesClient, SecretsClient, SectorClient
from orbitlab.redis.models import FileStep, ScriptStep

from .base import Workflow, WorkflowPayload


class ImagePayload(WorkflowPayload):
    """Default payload for images."""

    id: str


class ImageDownloadV1(Workflow):

    TYPE: str = "image.download"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ImagePayload] = ImagePayload
    payload: ImagePayload

    async def validate(self) -> None:
        if not await ImagesClient().image_exists(image_type="base", id=self.payload.id):
            return await self.fail(f"Base Image {self.payload.id} does not exist")

    async def provision(self) -> None:
        client = ImagesClient()
        proxmox = ProxmoxComputeTemplates()
        base_image = await client.get_image(image_type="base", id=self.payload.id)

        if base_image.state.volume_id:
            latest_image = (await proxmox.get_vendored_images()).get_os_image(os=base_image.config.os)
            if latest_image.filename == base_image.config.filename:
                return await self.succeed(f"Image {self.payload.id} already on the latest version.")
            
            await self.log(f"Deleting old {base_image.config.id} volume: {base_image.state.volume_id}")
            await proxmox.delete_image(
                node=base_image.config.node,
                storage=base_image.config.storage,
                volume_id=base_image.state.volume_id,
            )
        
        params = {
            "content": "import",
            "url": base_image.config.download_url,
            "filename": base_image.config.filename,
            "checksum": base_image.config.checksum,
            "checksum-algorithm": base_image.config.checksum_algorithm,
        }
        await self.log(f"Downloading {base_image.config.id} with params: {params}")
        volume_id = await proxmox.download_image(
            node=base_image.config.node, storage=base_image.config.storage, params=params,
        )
        await client.set_base_image_downloaded(id=self.payload.id, volume_id=volume_id)
        await self.succeed(f"Download of {self.payload.id} complete.")


class ImageDeletePayload(ImagePayload):
    """Payload for deleting appliances."""

    image_type: Literal["custom", "base"]


class ImageDeleteV1(Workflow):
    """Workflow for changing the state of an LXC container."""

    TYPE: str = "image.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ImageDeletePayload] = ImageDeletePayload
    payload: ImageDeletePayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        if not await ImagesClient().image_exists(image_type=self.payload.image_type, id=self.payload.id):
            await self.succeed(f"{self.payload.image_type.capitalize()} image {self.payload.id} doesn't exist or already deleted.")

    async def provision(self) -> None:
        """Delete the image and manifest."""
        client = ImagesClient()
        proxmox = ProxmoxComputeTemplates()
        image = await client.get_image(image_type=self.payload.image_type, id=self.payload.id)
        
        if image.state.volume_id and await proxmox.volume_id_exists(node=image.config.node, storage=image.config.storage, volume_id=image.state.volume_id):
            await self.log(f"Deleting volume id: {image.state.volume_id}")
            await proxmox.delete_image(node=image.config.node, storage=image.config.storage, volume_id=image.state.volume_id)

        await self.log(message=f"Deleting image {image.config.id}")
        await client.delete_image(image_type=self.payload.image_type, id=self.payload.id)
        await self.succeed(f"Deleted {self.payload.image_type.capitalize()} image {self.payload.id}")


class CustomImagePayload(ImagePayload):
    """Payload for LXC workflows."""

    vmid: int = 0


class CreateCustomImageV1(Workflow):
    """Create a custom VM Image."""

    TYPE: str = "image.custom"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[CustomImagePayload] = CustomImagePayload
    payload: CustomImagePayload

    async def validate(self) -> None:
        """Validate the custom image manifest exists and initialize redis tracking."""
        client = ImagesClient()
        if not await client.image_exists(image_type="custom", id=self.payload.id):
            return await self.fail(f"Custom Image {self.payload.id} does not exist")
        
        await client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.PENDING)

    async def provision(self) -> None:
        """Provision the VM compute instance and ensure it's online."""
        client = ImagesClient()
        proxmox = ProxmoxCompute()
        image = await client.get_image(image_type="custom", id=self.payload.id)
        
        self.payload.vmid = await proxmox.get_next_vmid()

        await client.update_workflow_logs(id=self.payload.id, logs=[f"Creating VMID {self.payload.vmid}"], reset=True)
        
        params = image.config.workflow_create_params(
            vmid=self.payload.vmid,
            password=SecretsClient.generate_random_password(),
            sector_dns=(await SectorClient().get(id=image.config.sector)).config.dns_address.ip
        )
        await self.log(f"Creating {self.payload.vmid}@{image.config.node} with params: {params}")
        await proxmox.create_vm(params=params, node=image.config.node)
        
        await self.log(f"Resizing {self.payload.vmid}@{image.config.node} to {image.config.disk_size}G")
        await proxmox.resize_disk(vmid=self.payload.vmid, disk_size=image.config.disk_size)
        
        await self.log(f"Starting {self.payload.vmid}@{image.config.node}")
        await client.update_workflow_logs(id=self.payload.id, logs=[f"Starting {self.payload.vmid}"])
        await client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.STARTING)
        await proxmox.start(vmid=self.payload.vmid)
        
        await self.log(f"Waiting for agent on {self.payload.vmid}@{image.config.node}")
        await proxmox.wait_for_agent(vmid=self.payload.vmid)

    async def configure(self) -> None:
        """Run custom image configuration steps, then stop the instance."""
        client = ImagesClient()
        proxmox = ProxmoxCompute()
        image = await client.get_image(image_type="custom", id=self.payload.id)

        await client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.RUNNING)

        for step in image.config.steps:
            await client.update_workflow_logs(id=self.payload.id, logs=[f"Executing Step: {step.name}"])

            if isinstance(step, FileStep):
                for file in step.files:
                    await asyncio.gather(
                        await client.update_workflow_logs(
                            id=self.payload.id,
                            logs=[f"Pushing File: {file.source} to {file.destination}"],
                        ),
                        proxmox.agent_write_file(vmid=self.payload.vmid, source=file.source, destination=file.destination)
                    )
            elif isinstance(step, ScriptStep):
                status = await proxmox.agent_execute_script(vmid=self.payload.vmid, script=step.script)
                if status.exitcode and status.exitcode > 0:
                    await client.update_workflow_logs(id=self.payload.id, logs=status.logs)
                    return await self.fail(f"{step.name} exited with code {status.exitcode}")
                await client.update_workflow_logs(id=self.payload.id, logs=status.logs)

        if not image.config.steps:
            await client.update_workflow_logs(id=self.payload.id, logs=["No steps to execute"])

        await client.update_workflow_logs(id=self.payload.id, logs=[f"Shutting Down VMID {self.payload.vmid}"])
        await proxmox.shutdown(vmid=self.payload.vmid)

    async def finalize(self) -> None:
        """Convert the VM disk to image via qemu-img convert."""
        client = ImagesClient()
        proxmox = ProxmoxComputeTemplates()
        image = await client.get_image(image_type="custom", id=self.payload.id)

        await client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.FINALIZING)
        await client.update_workflow_logs(id=self.payload.id, logs=[f"Generating image from VMID {self.payload.vmid}"])
        
        volume_id = await proxmox.generate_image(
            vmid=self.payload.vmid,
            name=image.config.name,
            disk_storage=image.config.disk_storage,
            image_storage=image.config.image_storage,
        )
        await client.workflow_succeeded(id=self.payload.id, volume_id=volume_id)
        await ProxmoxCompute().terminate(vmid=self.payload.vmid)

    async def on_succeed(self) -> None:
        """Set the status to SUCCEEDED."""
        await ImagesClient().set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.SUCCEEDED)

    async def on_failure(self) -> None:
        """Set the status to FAILED."""
        await ImagesClient().set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.FAILED)
