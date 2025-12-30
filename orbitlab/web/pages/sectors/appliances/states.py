"""OrbitLab Sector Appliances States."""

import ipaddress
import re

import httpx
import reflex as rx
from pydantic import BaseModel, computed_field

from orbitlab.clients.proxmox.appliances import ProxmoxAppliances
from orbitlab.constants import NetworkSettings
from orbitlab.data_types import OrbitLabApplianceType, StorageContentType
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.web.states.utilities import CacheBuster


class SectorSpec(BaseModel):
    """Sector specification model for calculating available IP addresses."""

    cidr_block: str

    @computed_field
    @property
    def available_ips(self) -> int:
        """Calculate the number of available IP addresses in the network."""
        usable = ipaddress.IPv4Network(self.cidr_block).num_addresses - 2
        return max(usable - NetworkSettings.RESERVED_USABLE_IPS, 0)

    @computed_field
    @property
    def available_range(self) -> str:
        """Get the available IP address range for the network."""
        min_required_to_render = 11
        hosts = list(ipaddress.IPv4Network(self.cidr_block).hosts())
        if len(hosts) > min_required_to_render:
            return f"{hosts[NetworkSettings.RESERVED_USABLE_IPS]} - {hosts[-1]}"
        return ""


class SectorAppliancesTableState(CacheBuster, rx.State):
    """Sector Appliances Table State."""

    @rx.var(deps=["_cached_sector_gateway"])
    def sector_gateway(self) -> str:
        """Get the gateway appliance name from the cluster manifest."""
        name = next(iter(ClusterManifest.get_existing()), None)
        if name:
            cluster_manifest = ClusterManifest.load(name=name)
            if match := re.match(
                pattern=r"sector-gateway-(\d+\.\d+\.\d).tar.gz",
                string=cluster_manifest.metadata.sector_gateway_appliance,
            ):
                return match.groups()[0]
        return "Err"

    @rx.var(deps=["_cached_sector_dns"])
    def sector_dns(self) -> str:
        """Get the gateway appliance name from the cluster manifest."""
        name = next(iter(ClusterManifest.get_existing()), None)
        if name:
            cluster_manifest = ClusterManifest.load(name=name)
            if match := re.match(
                pattern=r"sector-dns-(\d+\.\d+\.\d).tar.gz",
                string=cluster_manifest.metadata.sector_dns_appliance,
            ):
                return match.groups()[0]
        return "Err"

    @rx.var(deps=["_cached_backplane_dns"])
    def backplane_dns(self) -> str:
        """Get the gateway appliance name from the cluster manifest."""
        name = next(iter(ClusterManifest.get_existing()), None)
        if name:
            cluster_manifest = ClusterManifest.load(name=name)
            if match := re.match(
                pattern=r"backplane-dns-(\d+\.\d+\.\d).tar.gz",
                string=cluster_manifest.metadata.backplane_dns_appliance,
            ):
                return match.groups()[0]
        return "Err"

    @rx.var(deps=["_cached_latest_versions"])
    def latest_versions(self) -> dict[OrbitLabApplianceType, str]:
        """Get the latest gateway appliance version from Proxmox."""
        latest = {}
        for appliance_type in OrbitLabApplianceType:
            try:
                latest_release = ProxmoxAppliances().get_latest_release(appliance_type=appliance_type)
            except httpx.HTTPStatusError:
                continue
            else:
                latest[appliance_type] = latest_release.version
        return latest

    @rx.var
    def latest_sector_gateway_version(self) -> str:
        """Get the latest gateway appliance version from Proxmox."""
        return self.latest_versions.get(OrbitLabApplianceType.SECTOR_GATEWAY, "Err")

    @rx.var
    def latest_sector_dns_version(self) -> str:
        """Get the latest gateway appliance version from Proxmox."""
        return self.latest_versions.get(OrbitLabApplianceType.SECTOR_DNS, "Err")

    @rx.var
    def latest_backplane_dns_version(self) -> str:
        """Get the latest gateway appliance version from Proxmox."""
        return self.latest_versions.get(OrbitLabApplianceType.BACKPLANE_DNS, "Err")

    @rx.event
    async def download_appliance(self, appliance_type: OrbitLabApplianceType) -> None:
        """Download the latest OrbitLab appliance of the given type and update the cluster manifest."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        storage = cluster_manifest.spec.defaults.storage.vztmpl or \
            cluster_manifest.default_node().get_storage(content_type=StorageContentType.VZTMPL)
        latest_appliance = ProxmoxAppliances().download_latest_orbitlab_appliance(
            storage=storage, appliance_type=appliance_type,
        )
        match appliance_type:
            case OrbitLabApplianceType.SECTOR_GATEWAY:
                cluster_manifest.metadata.sector_gateway_appliance = latest_appliance
            case OrbitLabApplianceType.BACKPLANE_DNS:
                cluster_manifest.metadata.backplane_dns_appliance = latest_appliance
            case OrbitLabApplianceType.SECTOR_DNS:
                cluster_manifest.metadata.sector_dns_appliance = latest_appliance
        cluster_manifest.save()
