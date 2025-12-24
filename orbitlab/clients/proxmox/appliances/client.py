"""Proxmox Appliances Client."""

from typing import TYPE_CHECKING

import httpx

from orbitlab.clients.proxmox.base import Proxmox, Task
from orbitlab.data_types import ApplianceType, OrbitLabApplianceType

from .models import ApplianceInfo, Appliances, LatestRelease, StoredAppliances

if TYPE_CHECKING:
    from orbitlab.manifest.appliances import BaseApplianceManifest


class ProxmoxAppliances(Proxmox):
    """Client for managing Proxmox appliances."""

    def get_latest_release(self, appliance_type: OrbitLabApplianceType) -> LatestRelease:
        """Get the latest release from a given repository."""
        with httpx.Client() as client:
            response = client.get(f"https://api.github.com/repos/OrbitLab-OSS/{appliance_type}/releases/latest")
            response.raise_for_status()
            return LatestRelease.model_validate(response.json())

    def list_appliances(self, appliance_type: ApplianceType | None = None) -> list[ApplianceInfo]:
        """List available LXC appliances on the specified Proxmox node."""
        appliances = self.get(f"/nodes/{self.__node__}/aplinfo", model=Appliances)
        match appliance_type:
            case ApplianceType.SYSTEM:
                return appliances.system_appliances()
            case ApplianceType.TURNKEY:
                return appliances.turnkey_appliances()
            case _:
                return appliances.root

    def download_appliance(self, appliance: "BaseApplianceManifest") -> None:
        """Download an LXC appliance to the specified storage on a Proxmox node."""
        params = {"storage": appliance.spec.storage, "template": appliance.spec.template}
        task = self.create(path=f"/nodes/{appliance.spec.node}/aplinfo", model=Task, **params)
        self.wait_for_task(node=task.node, upid=task.upid)

    def download_latest_orbitlab_appliance(self, storage: str, appliance_type: OrbitLabApplianceType) -> str:
        """Download the latest appliance template from GitHub releases."""
        latest = self.get_latest_release(appliance_type=appliance_type)
        appliance = latest.get_appliance_asset()
        checksum_algorithm, checksum = appliance.digest.split(":")
        params = {
            "content": "vztmpl",
            "url": appliance.browser_download_url,
            "filename": appliance.name,
            "checksum": checksum,
            "checksum-algorithm": checksum_algorithm,
        }
        task = self.create(path=f"/nodes/{self.__node__}/storage/{storage}/download-url", model=Task, **params)
        self.wait_for_task(node=task.node, upid=task.upid)
        return appliance.name

    def list_stored_appliances(self, node: str, storage: str) -> StoredAppliances:
        """List stored appliance templates in the specified storage on a Proxmox node."""
        params = {"content": "vztmpl"}
        return self.get(f"/nodes/{node}/storage/{storage}/content", model=StoredAppliances, **params)
