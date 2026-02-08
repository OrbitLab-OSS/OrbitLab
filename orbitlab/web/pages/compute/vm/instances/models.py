"""Orbitlab VM Instances Models."""

from pydantic import BaseModel

from orbitlab.manifest.compute_templates.images import BaseImageManifest, CustomImageManifest


class CreateVMForm(BaseModel):
    """Data model for creating a virtual machine (VM) instance."""

    node: str
    image: str
    name: str
    storage: str
    disk_size: int
    cores: int
    sockets: int
    memory: int
    password: str
    sector: str

    @property
    def volume_id(self) -> str:
        """Return the volume ID for the selected image, or an empty string for custom images."""
        if self.image in BaseImageManifest.get_existing():
            return BaseImageManifest.load(name=self.image).volume_id
        return CustomImageManifest.load(name=self.image).volume_id
