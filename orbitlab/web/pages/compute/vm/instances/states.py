"""OrbitLab VM Instances States."""

from datetime import timedelta

import reflex as rx

from orbitlab.data_types import StorageContentType
from orbitlab.manifest.compute_instances import VMManifest
from orbitlab.manifest.compute_templates import BaseImageManifest, CustomImageManifest
from orbitlab.proxmox import Proxmox
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.utilities import CacheBuster, get_redis


async def get_redis_value(manifest_name: str, key: str) -> str | None:
    """Retrieve a value from Redis for a given manifest and key."""
    redis = get_redis()
    try:
        value = await redis.hget(name=f"ol:vm:{manifest_name}", key=key)
        if isinstance(value, bytes):
            return value.decode()
    except RuntimeError:
        return None
    else:
        return None

class VMInstancesTableState(CacheBuster, rx.State):
    """State management for running VMs."""

    instance_to_terminate: rx.Field[str] = rx.field(default="")

    @rx.var(deps=["_cached_running"])
    def running(self) -> list[VMManifest]:
        """Return a list of running VM instances."""
        return [VMManifest.load(name=name) for name in VMManifest.get_existing()]

    @rx.var(interval=timedelta(hours=12))
    async def address_map(self) -> dict[str, str | None]:
        """Return a mapping of VM manifest names to their IPv4 addresses."""
        return {
            manifest.name: await get_redis_value(manifest_name=manifest.name, key="ipv4")
            for manifest in self.running
        }

    @rx.var
    async def state_map(self) -> dict[str, str | None]:
        """Return a mapping of VM manifest names to their states."""
        return {
            manifest.name: await get_redis_value(manifest_name=manifest.name, key="state")
            for manifest in self.running
        }


def _all_images() -> dict[str, str]:
    images = {
        f"{BaseImageManifest.load(name=name).metadata.os} ({name})": name
        for name in BaseImageManifest.get_existing()
    }
    images.update({
        f"{CustomImageManifest.load(name=name).metadata.name} ({name})": name
        for name in CustomImageManifest.get_existing()
    })
    return images


class LaunchVMDialogState(rx.State):
    """State management for the Launch VM dialog, handling form data and available options."""

    form_data: rx.Field[dict] = rx.field(default_factory=dict)

    available_images: rx.Field[dict[str, str]] = rx.field(default_factory=_all_images)

    memory_gb: rx.Field[int] = rx.field(default=2)
    cores: rx.Field[int] = rx.field(default=2)
    sockets: rx.Field[int] = rx.field(default=1)
    disk_size_gb: rx.Field[int] = rx.field(default=10)
    sector: rx.Field[str] = rx.field(default="")

    @rx.var
    async def available_disk_storages(self) -> list[str]:
        """Return a list of available disk storage names for the selected node."""
        node = await self.node
        if node:
            return Proxmox().list_storages_for_node(node=node, content_type=StorageContentType.IMAGES)
        return []

    @rx.var
    def name(self) -> str:
        """VM hostname."""
        return self.form_data.get("name", "")

    @rx.var
    async def node(self) -> str:
        """VM Proxmox node."""
        if "node" in self.form_data:
            return self.form_data["node"]
        return await self.get_var_value(ClusterDefaults.proxmox_node)

    @rx.var
    def image(self) -> str:
        """VM image."""
        return self.form_data.get("image", "")

    @rx.var
    async def disk_storage(self) -> str:
        """VM Disk Image store."""
        if "disk_store" in self.form_data:
            return self.form_data["disk_store"]
        return await self.get_var_value(ClusterDefaults.import_storage)

    @rx.var
    async def sectors(self) -> dict[str, str]:
        """Get a mapping of sector display names to sector names."""
        return await self.get_var_value(ClusterDefaults.available_sectors)
