"""OrbitLab LXC States."""

import reflex as rx

from orbitlab.data_types import StorageContentType
from orbitlab.manifest.appliances import BaseApplianceManifest, CustomApplianceManifest
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.lxc import LXCManifest
from orbitlab.manifest.nodes import NodeManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.web.utilities import CacheBuster


class LXCsState(CacheBuster, rx.State):
    """State management for running LXC containers."""

    @rx.var(deps=["_cached_running"])
    def running(self) -> list[LXCManifest]:
        """Return a list of running LXCManifest instances."""
        return [LXCManifest.load(name=name) for name in LXCManifest.get_existing()]


def _all_appliances() -> list[str]:
    return BaseApplianceManifest.get_existing() + CustomApplianceManifest.get_existing()


class LaunchLXCState(rx.State):
    """State management for launching LXC containers, including form data and available options."""

    form_data: rx.Field[dict] = rx.field(default_factory=dict)

    appliances: rx.Field[list[str]] = rx.field(default_factory=_all_appliances)

    memory_gb: rx.Field[int] = rx.field(default=2)
    swap_gb: rx.Field[int] = rx.field(default=1)
    disk_size_gb: rx.Field[int] = rx.field(default=8)
    cores: rx.Field[int] = rx.field(default=2)
    sector: rx.Field[str] = rx.field(default="")

    @rx.var
    def available_rootfs(self) -> list[str]:
        """Get the available rootfs options for the selected node."""
        if self.node:
            return NodeManifest.load(name=self.node).list_storages(content_type=StorageContentType.ROOTDIR)
        return []

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
    def subnet(self) -> str:
        """LXC Subnet."""
        return self.form_data.get("subnet", "")

    @rx.var
    def rootfs(self) -> str:
        """LXC Root FS store."""
        if "rootfs" in self.form_data:
            return self.form_data["rootfs"]
        cluster = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        return cluster.get_storage(content_type=StorageContentType.ROOTDIR)

    @rx.var
    def sectors(self) -> dict[str, str]:
        """Available Sectors."""
        """Get a mapping of sector display names to sector names."""
        return {
            f"{sector.name} ({sector.spec.cidr_block})": sector.name
            for sector in [SectorManifest.load(name=name) for name in SectorManifest.get_existing()]
        }

    @rx.var
    def subnets(self) -> dict[str, str]:
        """Available Subnets in selected Sector."""
        if self.sector:
            sector_manifest = SectorManifest.load(name=self.sector)
            return {
                (
                    f"{subnet.name} ({subnet.cidr_block}, "
                    f"Available: {sector_manifest.get_available_ips(subnet_name=subnet.name)})"
                ): subnet.name
                for subnet in sector_manifest.spec.subnets
            }
        return {}
