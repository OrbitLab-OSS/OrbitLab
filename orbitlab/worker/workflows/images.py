"""VM Image (QCOW2/RAW) Workflows."""

from datetime import UTC, datetime
from typing import Literal

import reflex as rx

from orbitlab.data_types import WorkflowStatus
from orbitlab.manifest.compute_templates import BaseImageManifest, CustomImageManifest
from orbitlab.manifest.compute_templates.workflow_models import FileStep, ScriptStep
from orbitlab.web.pages.compute.vm.images.states import BaseImagesTableState, CustomImagesTableState
from orbitlab.worker.workflows.utilities import VMImageUtils, VMUtils

from .base import Workflow, WorkflowPayload


class ImagePayload(WorkflowPayload):
    """Default payload for images."""

    manifest: str

    @property
    def redis_name(self) -> str:
        """Image Workflow Key."""
        return f"ol:image:{self.manifest}"


class ImageDownloadV1(Workflow, VMImageUtils):

    TYPE: str = "image.download"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ImagePayload] = ImagePayload
    payload: ImagePayload

    async def validate(self) -> None:
        if self.payload.manifest not in BaseImageManifest.get_existing():
            await self.fail(f"Manifest for {self.payload.manifest} does not exist")
            return
        
    async def provision(self) -> None:
        """Delete previous image, if necessary."""
        manifest = BaseImageManifest.load(name=self.payload.manifest)
        await self.download(params=manifest.download_params(), node=manifest.spec.node, storage=manifest.spec.storage)
        manifest.metadata.download_date = datetime.now(tz=UTC)
        manifest.spec.volume_id = await self.get_volume_id(
            node=manifest.spec.node, storage=manifest.spec.storage, filename=manifest.spec.filename,
        )
        manifest.save()
        await self.succeed(message=f"Download of {manifest.spec.filename} complete.")

    async def on_succeed(self) -> None:
        """Emit reflex events to notify of success."""
        await self.emit_reflex_events(events=[BaseImagesTableState.cache_clear("available_images")])

    async def on_failure(self) -> None:
        """Delete manifest if it exists and we're not updating."""
        if self.payload.manifest in BaseImageManifest.get_existing():
            BaseImageManifest.load(name=self.payload.manifest).delete()
        await self.emit_reflex_events(events=[BaseImagesTableState.cache_clear("available_images")])


class ImageUpdateV1(Workflow, VMImageUtils):

    TYPE: str = "image.update"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ImagePayload] = ImagePayload
    payload: ImagePayload

    async def validate(self) -> None:
        if self.payload.manifest not in BaseImageManifest.get_existing():
            await self.fail(f"Manifest for {self.payload.manifest} does not exist")
            return
        
        manifest = BaseImageManifest.load(name=self.payload.manifest)
        latest_images = self.proxmox_compute_templates.get_vendored_images()
        latest = latest_images.get_os_image(os=manifest.metadata.os)
        if latest.filename == manifest.spec.filename:
            return await self.succeed(f"Image {manifest.metadata.os} is already on the latest version.")
        
    async def provision(self) -> None:
        """Delete previous image, if necessary."""
        manifest = BaseImageManifest.load(name=self.payload.manifest)
        
        await self.delete(node=manifest.spec.node, storage=manifest.spec.storage, volume_id=manifest.spec.volume_id)
        
        latest_images = self.proxmox_compute_templates.get_vendored_images()
        latest = latest_images.get_os_image(os=manifest.metadata.os)
        await self.download(params=latest.download_params(), node=manifest.spec.node, storage=manifest.spec.storage)
        volume_id = await self.get_volume_id(node=manifest.spec.node, storage=manifest.spec.storage, filename=latest.filename)
        manifest.update(volume_id=volume_id, image=latest)
        await self.succeed(message=f"Download of {manifest.spec.filename} complete.")

    async def on_succeed(self) -> None:
        """Emit reflex events to notify of success."""
        await self.emit_reflex_events(events=[BaseImagesTableState.cache_clear("available_images")])


class ImageDeletePayload(ImagePayload):
    """Payload for deleting appliances."""

    image_type: Literal["custom", "base"]


class ImageDeleteV1(Workflow, VMImageUtils):
    """Workflow for changing the state of an LXC container."""

    TYPE: str = "image.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ImageDeletePayload] = ImageDeletePayload
    payload: ImageDeletePayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        if self.payload.image_type == "base" and self.payload.manifest not in BaseImageManifest.get_existing():
            await self.succeed(f"Base image {self.payload.manifest} doesn't exist or already deleted.")
            return
        if self.payload.image_type == "custom" and self.payload.manifest not in CustomImageManifest.get_existing():
            await self.succeed(f"Custom image {self.payload.manifest} doesn't exist or already deleted.")
            return

        if self.payload.image_type == "base":
            manifest = BaseImageManifest.load(name=self.payload.manifest)
            storage = manifest.spec.storage
        else:
            manifest = CustomImageManifest.load(name=self.payload.manifest)
            storage = manifest.spec.image_storage

        images = self.proxmox_compute_templates.list_stored_images(node=manifest.spec.node, storage=storage)
        image = manifest.spec.filename if isinstance(manifest, BaseImageManifest) else manifest.name
        if not images.image_exists(image=image):
            manifest.delete()
            await self.succeed(f"Image {image} already deleted or doesn't exist.")

    async def provision(self) -> None:
        """Delete the image and manifest."""
        if self.payload.image_type == "base":
            manifest = BaseImageManifest.load(name=self.payload.manifest)
        else:
            manifest = CustomImageManifest.load(name=self.payload.manifest)

        storage = manifest.spec.storage if isinstance(manifest, BaseImageManifest) else manifest.spec.image_storage
        await self.delete(node=manifest.spec.node, storage=storage, volume_id=manifest.spec.volume_id)

        await self.log(message=f"Deleting manifest {manifest.name}")
        manifest.delete()
        if self.payload.image_type == "custom":
            await self.redis.hdel(self.payload.redis_name, "logs", "status")
        await self.succeed(f"Deleted {self.payload.manifest}")

    async def on_succeed(self) -> None:
        """Emit reflex events to notify of success."""
        events = [
            rx.toast.success(message=f"Appliance {self.payload.manifest} deleted."),
        ]

        if self.payload.image_type == "base":
            events.append(BaseImagesTableState.cache_clear("available_images"))
        else:
            events.append(CustomImagesTableState.cache_clear("custom_images"))
        await self.emit_reflex_events(events=events)

    async def on_failure(self) -> None:
        """Handle workflow failure."""


class CustomImagePayload(ImagePayload):
    """Payload for LXC workflows."""

    vmid: int = 0


class CreateCustomImageV1(Workflow, VMUtils, VMImageUtils):
    """Create a custom VM Image."""

    TYPE: str = "image.custom"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[CustomImagePayload] = CustomImagePayload
    payload: CustomImagePayload

    async def validate(self) -> None:
        """Validate the custom image manifest exists and initialize redis tracking."""
        if self.payload.manifest not in CustomImageManifest.get_existing():
            await self.fail(f"Manifest for {self.payload.manifest} does not exist")
            return
        await self.redis.hset(name=self.payload.redis_name, key="status", value=WorkflowStatus.STARTING.value)
        await self.redis.hset(name=self.payload.redis_name, key="logs", value="")
        await self.emit_reflex_events(events=[CustomImagesTableState.cache_clear("custom_images")])

    async def provision(self) -> None:
        """Provision the VM compute instance and ensure it's online."""
        manifest = CustomImageManifest.load(name=self.payload.manifest)
        self.payload.vmid = self.proxmox_compute.get_next_vmid()

        await self.__update_logs__(redis_name=self.payload.redis_name, lines=[f"Creating VMID {self.payload.vmid}"])
        await self.create(
            params=manifest.workflow_params(vmid=self.payload.vmid),
            node=manifest.spec.node,
            disk_size=manifest.spec.disk_size,
        )
        await self.start(vmid=self.payload.vmid)
        await self.wait_for_agent(vmid=self.payload.vmid)

    async def configure(self) -> None:
        """Run custom image configuration steps, then stop the instance."""
        manifest = CustomImageManifest.load(name=self.payload.manifest)

        await self.redis.hset(name=self.payload.redis_name, key="status", value=WorkflowStatus.RUNNING.value)
        await self.emit_reflex_events(events=[CustomImagesTableState.cache_clear("custom_images")])

        for step in manifest.spec.steps:
            await self.__update_logs__(redis_name=self.payload.redis_name, lines=[f"Executing Step: {step.name}"])
            if isinstance(step, FileStep):
                for file in step.files:
                    await self.__update_logs__(
                        redis_name=self.payload.redis_name,
                        lines=[f"Pushing File: {file.source} to {file.destination}"],
                    )
                    await self.file_write(vmid=self.payload.vmid, file=file)
            elif isinstance(step, ScriptStep):
                status = await self.execute_script(vmid=self.payload.vmid, script=step)
                if status.exitcode and status.exitcode > 0:
                    await self.__update_logs__(redis_name=self.payload.redis_name, lines=status.logs)
                    await self.fail(f"{step.name} exited with code {status.exitcode}")
                    return
                await self.__update_logs__(redis_name=self.payload.redis_name, lines=status.logs)

        if not manifest.spec.steps:
            await self.__update_logs__(redis_name=self.payload.redis_name, lines=["No steps to execute"])

        await self.__update_logs__(
            redis_name=self.payload.redis_name, lines=[f"Shutting Down VMID {self.payload.vmid}"],
        )
        await self.stop(vmid=self.payload.vmid, shutdown=True)

    async def finalize(self) -> None:
        """Convert the VM disk to image via qemu-img convert."""
        manifest = CustomImageManifest.load(name=self.payload.manifest)

        await self.redis.hset(name=self.payload.redis_name, key="status", value=WorkflowStatus.FINALIZING.value)
        await self.emit_reflex_events(events=[CustomImagesTableState.cache_clear("custom_images")])

        await self.__update_logs__(
            redis_name=self.payload.redis_name,
            lines=[f"Generating image from VMID {self.payload.vmid}"],
        )
        await self.generate_image(
            vmid=self.payload.vmid,
            name=manifest.name,
            disk_storage=manifest.spec.disk_storage,
            image_storage=manifest.spec.image_storage,
        )
        if not manifest.spec.volume_id:
            manifest.spec.volume_id = await self.get_volume_id(node=manifest.spec.node, storage=manifest.spec.image_storage, filename=manifest.name)
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

    async def __cleanup__(self) -> None:
        """Cleanup workflow resources and update manifest metadata."""
        if self.payload.vmid:
            await self.terminate(vmid=self.payload.vmid)
        await self.emit_reflex_events(events=[CustomImagesTableState.cache_clear("custom_images")])

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
        await self.emit_reflex_events(events=[CustomImagesTableState.cache_clear("logs")])
