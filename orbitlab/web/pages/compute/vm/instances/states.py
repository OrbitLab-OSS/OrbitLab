"""OrbitLab VM Instances States."""

import reflex as rx

from orbitlab.clients.proxmox import Proxmox
from orbitlab.data_types import StorageContentType
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.compute_instances import VMManifest
from orbitlab.manifest.compute_templates import BaseImageManifest, CustomImageManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.web.utilities import CacheBuster


class VMInstancesTableState(CacheBuster, rx.State):
    """State management for running LXC containers."""

    @rx.var(deps=["_cached_running"])
    def running(self) -> list[VMManifest]:
        """Return a list of running LXCManifest instances."""
        return [VMManifest.load(name=name) for name in VMManifest.get_existing()]


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
    def available_disk_storages(self) -> list[str]:
        """Return a list of available disk storage names for the selected node."""
        if self.node:
            return Proxmox().list_storages_for_node(node=self.node, content_type=StorageContentType.IMAGES)
        return []

    @rx.var
    def name(self) -> str:
        """VM hostname."""
        return self.form_data.get("name", "")

    @rx.var
    def node(self) -> str:
        """VM Proxmox node."""
        default_node = ""
        if cluster := next(iter(ClusterManifest.get_existing()), None):
            default_node = ClusterManifest.load(name=cluster).spec.defaults.node
        return self.form_data.get("node", default_node)

    @rx.var
    def image(self) -> str:
        """VM image."""
        return self.form_data.get("image", "")

    @rx.var
    def disk_storage(self) -> str:
        """VM Disk Image store."""
        if "disk_store" in self.form_data:
            return self.form_data["disk_store"]
        if existing := ClusterManifest.get_existing():
            cluster = ClusterManifest.load(name=next(iter(existing)))
            return cluster.get_storage(content_type=StorageContentType.IMAGES)
        return ""

    @rx.var
    def sectors(self) -> dict[str, str]:
        """Get a mapping of sector display names to sector names."""
        return {
            f"{sector.name} ({sector.spec.cidr_block})": sector.name
            for sector in [SectorManifest.load(name=name) for name in SectorManifest.get_existing()]
        }
