"""Proxmox Appliances Client."""

import hashlib
from re import S
from string import Template

import httpx

from orbitlab.data_types import ApplianceType
from orbitlab.proxmox.base import Proxmox, Task
from orbitlab.proxmox.compute.models import VendoredImages

from .models import (
    ApplianceInfo,
    Appliances,
    OrbitLabAppliances,
    StoredAppliances,
    StoredImages,
    VolumeContentInfo,
)


class ProxmoxComputeTemplates(Proxmox):
    """Client for managing Proxmox compute templates (LXC appliances and VM images)."""

    async def get_infrastructure_appliances(self) -> OrbitLabAppliances:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://raw.githubusercontent.com/OrbitLab-OSS/Appliances/refs/heads/main/metadata/appliances.json")
            response.raise_for_status()
        return OrbitLabAppliances.model_validate(response.json())

    async def get_vendored_images(self) -> VendoredImages:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://raw.githubusercontent.com/OrbitLab-OSS/VendoredImages/refs/heads/main/metadata/images.json")
        response.raise_for_status()
        return VendoredImages.model_validate(response.json())

    async def list_appliances(self, appliance_type: ApplianceType | None = None) -> list[ApplianceInfo]:
        """List available LXC appliances on the specified Proxmox node."""
        appliances = await self.get(f"/nodes/{self.__node__}/aplinfo", model=Appliances)
        match appliance_type:
            case ApplianceType.SYSTEM:
                return appliances.system_appliances()
            case ApplianceType.TURNKEY:
                return appliances.turnkey_appliances()
            case _:
                return appliances.root

    async def list_stored_appliances(self, node: str, storage: str) -> StoredAppliances:
        """List stored appliance templates in the specified storage on a Proxmox node."""
        params = {"content": "vztmpl"}
        return await self.get(f"/nodes/{node}/storage/{storage}/content", model=StoredAppliances, **params)

    async def list_stored_images(self, node: str, storage: str) -> StoredImages:
        """List stored images in the specified storage on a Proxmox node."""
        params = {"content": "import"}
        return await self.get(f"/nodes/{node}/storage/{storage}/content", model=StoredImages, **params)

    async def volume_id_exists(self, node: str, storage: str, volume_id: str) -> bool:
        content_list: list[dict] = await self.get(f"/nodes/{node}/storage/{storage}/content", model=None)
        return bool(next(iter(item for item in content_list if item["volid"] == volume_id), None))

    async def get_volume_id(self, node: str, storage: str, filename: str) -> str:
        stored_images = await self.list_stored_images(node=node, storage=storage)
        return stored_images.get_image(filename=filename).volid

    async def _delete_template(self, node: str, storage: str, volume_id: str) -> None:
        task = await self.delete(path=f"/nodes/{node}/storage/{storage}/content/{volume_id}", model=Task)
        await self.wait_for_task(task=task)

    async def delete_appliance(self, node: str, storage: str, volume_id: str) -> None:
        """Delete a custom appliance from the specified Proxmox storage."""
        await self._delete_template(node=node, storage=storage, volume_id=volume_id)

    async def delete_image(self, node: str, storage: str, volume_id: str) -> None:
        """Delete a custom image from the specified Proxmox storage."""
        await self._delete_template(node=node, storage=storage, volume_id=volume_id)

    async def download_proxmox_managed_appliance(self, node: str, storage: str, template: str) -> str:
        task = await self.create(
            path=f"/nodes/{node}/aplinfo",
            model=Task,
            storage=storage,
            template=template,
        )
        await self.wait_for_task(task=task)
        stored = await self.list_stored_appliances(node=node, storage=storage)
        return stored.get_appliance(filename=template).volid

    async def download_appliance_from_url(self, node: str, storage: str, params: dict) -> str:
        task = await self.create(path=f"/nodes/{node}/storage/{storage}/download-url", model=Task, **params)
        await self.wait_for_task(task=task)
        stored = await self.list_stored_appliances(node=node, storage=storage)
        return stored.get_appliance(filename=params["filename"]).volid

    async def download_image(self, node: str, storage: str, params: dict) -> str:
        task = await self.create(path=f"/nodes/{node}/storage/{storage}/download-url", model=Task, **params)
        await self.wait_for_task(task=task)
        stored = await self.list_stored_images(node=node, storage=storage)
        return stored.get_image(filename=params["filename"]).volid

    async def download_infrastructure_appliance(self, storage: str, params: dict, node: str = "") -> str:
        if not node:
            node = self.__node__

        task = await self.create(path=f"/nodes/{node}/storage/{storage}/download-url", model=Task, **params)
        await self.wait_for_task(task=task)
        filename: str = params["filename"]
        if filename.endswith(".qcow2") or filename.endswith(".raw"):
            stored = await self.list_stored_images(node=node, storage=storage)
            return stored.get_image(filename=filename).volid
        else:
            stored = await self.list_stored_appliances(node=node, storage=storage)
            return stored.get_appliance(filename=filename).volid

    async def generate_image(self, vmid: int, name: str, disk_storage: str, image_storage: str) -> str:
        """Generate a QCOW2 image from a virtual machine disk and upload it to storage."""
        volume_id = await self.get_vm_root_volume_id(vmid=vmid)
        node = await self.get_node_for_vmid(vmid=vmid)
        volume = await self.get(
            path=f"/nodes/{node}/storage/{disk_storage}/content/{volume_id}",
            model=VolumeContentInfo,
        )
        temp_name = hashlib.sha256(volume_id.encode()).hexdigest()
        command = Template("qemu-img convert -p -O qcow2 $path /var/tmp/pveupload-$temp_name").safe_substitute(path=volume.path, temp_name=temp_name)
        async with await self.create_connection(node=node) as connection:
            await connection.run_command(command=command, check_output=True)

        params = {
            "content": "import",
            "filename": f"{name}.qcow2",
            "tmpfilename": f"/var/tmp/pveupload-{temp_name}",
        }
        task = await self.create(
            path=f"/nodes/{node}/storage/{image_storage}/upload",
            model=Task,
            **params,
        )
        await self.wait_for_task(task=task)
        stored_images = await self.list_stored_images(node=node, storage=image_storage)
        return stored_images.get_image(filename=params["filename"]).volid

    async def generate_appliance(self, vmid: int, appliance_id: str, storage: str) -> str:
        node = await self.get_node_for_vmid(vmid=vmid)
        params = {"vmid": vmid, "quiet": 1, "compress": "gzip", "dumpdir": "/var/tmp"}
        task = await self.create(path=f"/nodes/{node}/vzdump", model=Task, **params)
        await self.wait_for_task(task=task)

        temp_name = hashlib.sha256(appliance_id.encode()).hexdigest()
        command = f"mv /var/tmp/vzdump-lxc-{vmid}-*.tar.gz /var/tmp/pveupload-{temp_name}"
        async with await self.create_connection(node=node) as connection:
            await connection.run_command(command=command)

        params = {
            "content": "vztmpl",
            "filename": f"{appliance_id}.tar.gz",
            "tmpfilename": f"/var/tmp/pveupload-{temp_name}",
        }
        task = await self.create(path=f"/nodes/{node}/storage/{storage}/upload", model=Task, **params)
        await self.wait_for_task(task=task)
        
        stored = await self.list_stored_appliances(node=node, storage=storage)
        return stored.get_appliance(filename=params["filename"]).volid
