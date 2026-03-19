"""Proxmox Appliances Client."""

import httpx

from orbitlab.data_types import ApplianceType
from orbitlab.manifest.compute_templates import (
    BaseApplianceManifest,
    BaseImageManifest,
    CustomApplianceManifest,
    CustomImageManifest,
)
from orbitlab.proxmox.base import Proxmox, Task
from orbitlab.proxmox.compute.models import VendoredImages

from .models import (
    ApplianceInfo,
    Appliances,
    OrbitLabAppliances,
    StoredAppliances,
    StoredImages,
)


class ProxmoxComputeTemplates(Proxmox):
    """Client for managing Proxmox compute templates (LXC appliances and VM images)."""

    def get_infrastructure_appliances(self) -> OrbitLabAppliances:
        with httpx.Client() as client:
            response = client.get("https://raw.githubusercontent.com/OrbitLab-OSS/Appliances/refs/heads/main/metadata/appliances.json")
            response.raise_for_status()
        return OrbitLabAppliances.model_validate(response.json())

    def get_vendored_images(self) -> VendoredImages:
        with httpx.Client() as client:
            response = client.get("https://raw.githubusercontent.com/OrbitLab-OSS/VendoredImages/refs/heads/main/metadata/images.json")
        response.raise_for_status()
        return VendoredImages.model_validate(response.json())

    def download_vendored_image(self, manifest: BaseImageManifest) -> None:
        """Download a vendored image to the specified storage."""
        params = manifest.download_params()
        task = self.create(
            path=f"/nodes/{manifest.spec.node}/storage/{manifest.spec.storage}/download-url",
            model=Task,
            **params,
        )
        self.wait_for_task(task=task)

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

    def download_appliance(self, manifest: "BaseApplianceManifest") -> None:
        """Download an LXC appliance to the specified storage on a Proxmox node."""
        params = {"storage": manifest.spec.storage, "template": manifest.spec.template}
        task = self.create(path=f"/nodes/{manifest.spec.node}/aplinfo", model=Task, **params)
        self.wait_for_task(task=task)

    def list_stored_appliances(self, node: str, storage: str) -> StoredAppliances:
        """List stored appliance templates in the specified storage on a Proxmox node."""
        params = {"content": "vztmpl"}
        return self.get(f"/nodes/{node}/storage/{storage}/content", model=StoredAppliances, **params)

    def list_stored_images(self, node: str, storage: str) -> StoredImages:
        """List stored images in the specified storage on a Proxmox node."""
        params = {"content": "import"}
        return self.get(f"/nodes/{node}/storage/{storage}/content", model=StoredImages, **params)

    def delete_appliance(self, manifest: CustomApplianceManifest | BaseApplianceManifest) -> None:
        """Delete a custom appliance from the specified Proxmox storage."""
        task = self.delete(
            path=f"/nodes/{manifest.spec.node}/storage/{manifest.spec.storage}/content/{manifest.volume_id}",
            model=Task,
        )
        self.wait_for_task(task=task)

    def delete_image(self, manifest: CustomImageManifest | BaseImageManifest) -> None:
        """Delete a custom image from the specified Proxmox storage."""
        storage = manifest.spec.storage if isinstance(manifest, BaseImageManifest) else manifest.spec.image_storage
        task = self.delete(
            path=f"/nodes/{manifest.spec.node}/storage/{storage}/content/{manifest.volume_id}",
            model=Task,
        )
        self.wait_for_task(task=task)
