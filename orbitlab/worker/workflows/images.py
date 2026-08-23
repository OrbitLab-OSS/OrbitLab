"""VM Image (QCOW2/RAW) Workflows."""

import asyncio
from typing import Literal

from orbitlab.data_types import TemplateWorkflowStatus
from orbitlab.proxmox import Proxmox, ProxmoxAdapter
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
        proxmox = Proxmox()
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
        proxmox = Proxmox()
        
        image = await client.get_image(image_type=self.payload.image_type, id=self.payload.id)
        await asyncio.gather(
            self.log(f"Deleting {self.payload.image_type.capitalize()} image: {self.payload.id}"),
            proxmox.delete_image(node=image.config.node, storage=image.config.storage, volume_id=image.state.volume_id),
            client.delete_image(image_type=self.payload.image_type, id=self.payload.id),
        )
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
        proxmox = Proxmox()
        adapter = ProxmoxAdapter(proxmox)
        image = await client.get_image(image_type="custom", id=self.payload.id)
        sector_dns = (await SectorClient().get(id=image.config.sector)).config.dns_address.ip

        async def parameters(vmid: int) -> dict:
            params = image.config.workflow_create_params(
                vmid=vmid,
                password=SecretsClient.generate_random_password(),
                sector_dns=sector_dns,
            )
            await self.log(f"Creating custom image candidate VMID {vmid}@{image.config.node} with params: {self._redact_params(params)}")
            return params

        guest = await adapter.create_managed_guest(
            resource_id=f"image:{self.payload.id}:builder",
            instance_type="qemu",
            node=image.config.node,
            parameters=parameters,
        )
        self.payload.vmid = guest.vmid
        await client.update_workflow_logs(id=self.payload.id, logs=[f"Created VMID {self.payload.vmid}"], reset=True)
        
        await asyncio.gather(
            self.log(f"Resizing {self.payload.vmid}@{image.config.node} to {image.config.disk_size}G"),
            proxmox.resize_disk(vmid=self.payload.vmid, disk_size=image.config.disk_size, disk_id="scsi0"),
        )
        
        await client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.STARTING)
        await asyncio.gather(
            self.log(f"Starting {self.payload.vmid}@{image.config.node}"),
            client.update_workflow_logs(id=self.payload.id, logs=[f"Starting {self.payload.vmid}"]),
            proxmox.start(vmid=self.payload.vmid),
        )
        
        await asyncio.gather(
            self.log(f"Waiting for agent on {self.payload.vmid}@{image.config.node}"),
            proxmox.wait_for_agent(vmid=self.payload.vmid),
        )

    async def configure(self) -> None:
        """Run custom image configuration steps, then stop the instance."""
        client = ImagesClient()
        proxmox = Proxmox()
        image = await client.get_image(image_type="custom", id=self.payload.id)

        await client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.RUNNING)

        sysprep_commands = [
            "truncate -s 0 /etc/machine-id",
            "rm -f /var/lib/dbus/machine-id",
            "ln -sf /etc/machine-id /var/lib/dbus/machine-id",
            "rm -f /etc/ssh/ssh_host_*",
            "cloud-init clean --logs 2>/dev/null || true",
            "rm -f /root/.bash_history",
            "rm -rf /tmp/* /var/tmp/*",
        ]
        image.config.steps.append(ScriptStep(name="SysPrep", script="\n".join(sysprep_commands)))

        for step in image.config.steps:
            await client.update_workflow_logs(id=self.payload.id, logs=[f"Executing Step: {step.name}"])

            if isinstance(step, FileStep):
                for file in step.files:
                    await asyncio.gather(
                        client.update_workflow_logs(
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

        await asyncio.gather(
            client.update_workflow_logs(id=self.payload.id, logs=[f"Shutting Down VMID {self.payload.vmid}"]),
            proxmox.shutdown(vmid=self.payload.vmid),
        )

    async def finalize(self) -> None:
        """Convert the VM disk to image via qemu-img convert."""
        client = ImagesClient()
        proxmox = Proxmox()
        image = await client.get_image(image_type="custom", id=self.payload.id)

        await client.set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.FINALIZING)
        await asyncio.gather(
            client.update_workflow_logs(id=self.payload.id, logs=[f"Generating image from VMID {self.payload.vmid}"]),
        )
        
        volume_id = await proxmox.generate_image(
            vmid=self.payload.vmid,
            image_id=image.config.id,
            disk_storage=image.config.disk_storage,
            image_storage=image.config.storage,
        )
        await asyncio.gather(
            client.workflow_succeeded(id=self.payload.id, volume_id=volume_id),
            proxmox.terminate(vmid=self.payload.vmid),
        )

    async def on_succeed(self) -> None:
        """Set the status to SUCCEEDED."""
        await ImagesClient().set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.SUCCEEDED)

    async def on_failure(self) -> None:
        """Set the status to FAILED."""
        await ImagesClient().set_workflow_status(id=self.payload.id, workflow_status=TemplateWorkflowStatus.FAILED)
