"""OrbitLab LXC States."""

from datetime import timedelta

import reflex as rx

from orbitlab.data_types import StorageContentType
from orbitlab.manifest.compute_instances.lxc import LXCManifest
from orbitlab.manifest.compute_templates.appliances import BaseApplianceManifest, CustomApplianceManifest
from orbitlab.proxmox import Proxmox
from orbitlab.web.utilities import CacheBuster, get_redis


async def get_redis_value(manifest_name: str, key: str) -> str | None:
    """Retrieve a value from Redis for a given manifest and key."""
    redis = get_redis()
    ip = await redis.hget(name=f"ol:lxc:{manifest_name}", key=key)
    if isinstance(ip, bytes):
        return ip.decode()
    return None


class LXCInstancesTableState(CacheBuster, rx.State):
    """State management for running LXC containers."""

    instance_to_terminate: str = ""

    @rx.var(deps=["_cached_running"])
    def running(self) -> list[LXCManifest]:
        """Return a list of running LXCManifest instances."""
        return [LXCManifest.load(name=name) for name in LXCManifest.get_existing()]

    @rx.var(interval=timedelta(hours=12))
    async def address_map(self) -> dict[str, str | None]:
        """Return a mapping of LXC manifest names to their IPv4 addresses."""
        return {
            manifest.name: await get_redis_value(manifest_name=manifest.name, key="ipv4")
            for manifest in self.running
        }

    @rx.var
    async def state_map(self) -> dict[str, str | None]:
        """Return a mapping of LXC manifest names to their states."""
        return {
            manifest.name: await get_redis_value(manifest_name=manifest.name, key="state")
            for manifest in self.running
        }


def _all_appliances() -> dict[str, str]:
    _appliances = {
        f"{BaseApplianceManifest.load(name=name).spec.template} ({name})": name
        for name in BaseApplianceManifest.get_existing()
    }
    _appliances.update({
        f"{CustomApplianceManifest.load(name=name).metadata.name} ({name})": name
        for name in CustomApplianceManifest.get_existing()
    })
    return _appliances


class LaunchLXCState(rx.State):
    """State management for launching LXC containers, including form data and available options."""

    form_data: rx.Field[dict] = rx.field(default_factory=dict)
    appliances: rx.Field[dict[str, str]] = rx.field(default_factory=_all_appliances)
    memory_gb: rx.Field[int] = rx.field(default=2)
    swap_gb: rx.Field[int] = rx.field(default=1)
    disk_size_gb: rx.Field[int] = rx.field(default=8)
    cores: rx.Field[int] = rx.field(default=2)

    @rx.var
    def name(self) -> str:
        """LXC hostname."""
        return self.form_data.get("name", "")

    @rx.var
    def node(self) -> str:
        """LXC Proxmox node."""
        return self.form_data.get("node", "")

    @rx.var
    def appliance(self) -> str:
        """LXC appliance."""
        return self.form_data.get("appliance", "")

    @rx.var
    def rootfs(self) -> str:
        """LXC Root FS store."""
        return self.form_data.get("rootfs", "")

    @rx.var
    def sector(self) -> str:
        """LXC Sector."""
        return self.form_data.get("sector", "")

    @rx.var
    def available_rootfs(self) -> list[str]:
        """Get the available rootfs options for the selected node."""
        if self.node:
            return Proxmox().list_storages_for_node(node=self.node, content_type=StorageContentType.ROOTDIR)
        return []
