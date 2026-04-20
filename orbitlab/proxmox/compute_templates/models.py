"""Proxmox Appliances Client Models."""

from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, RootModel

from orbitlab.data_types import OrbitLabApplianceType


class ApplianceInfo(BaseModel):
    """Represents information about a Proxmox appliance."""

    architecture: str
    description: str
    headline: str
    info_page: Annotated[str, Field(alias="infopage")]
    location: str
    os: str
    package: str
    section: str
    sha512sum: str
    source: str
    template: str
    type: str
    version: str

    maintainer: Annotated[str | None, Field(default=None)]
    md5sum: Annotated[str | None, Field(default=None)]
    manage_url: Annotated[str | None, Field(alias="manageurl", default=None)]

    @property
    def is_turnkey(self) -> bool:
        """Indicates whether the appliance is a TurnKey appliance based on the presence of a management URL."""
        return bool(self.manage_url)


class Appliances(RootModel[list[ApplianceInfo]]):
    """Proxmox Appliances."""

    def system_appliances(self) -> list[ApplianceInfo]:
        """Return a list of system appliances (non-TurnKey appliances)."""
        return [apl for apl in self.root if not apl.is_turnkey]

    def turnkey_appliances(self) -> list[ApplianceInfo]:
        """Return a list of TurnKey appliances."""
        return [apl for apl in self.root if apl.is_turnkey]


class OrbitLabAppliance(BaseModel):

    filename: str
    digest: str
    size: int
    browser_download_url: str


class OrbitLabAppliances(BaseModel):
    """Represents the latest release information from the repository metadata."""

    version: str
    published_at: datetime
    appliances: list[OrbitLabAppliance]

    def get_appliance(self, appliance_type: OrbitLabApplianceType) -> OrbitLabAppliance:
        return next(appliance for appliance in self.appliances if appliance.filename.startswith(f"orbitlab-{appliance_type}"))


class StoredAppliance(BaseModel):
    """Represents a stored appliance template in Proxmox storage."""

    volid: str
    size: int
    format: str
    ctime: int

    @property
    def is_orbitlab_appliance(self) -> bool:
        """Check if this is an OrbitLab appliance based on the volume ID."""
        return "orbitlab-" in self.volid


class StoredAppliances(RootModel[list[StoredAppliance]]):
    """A list of stored appliances."""

    def __iter__(self) -> Iterator[StoredAppliance]:
        """Return an iterator over the stored appliances."""
        return iter([i for i in self.root if not i.is_orbitlab_appliance])

    def get_appliance(self, filename: str) -> StoredAppliance:
        appliance = next(iter([i for i in self.root if filename in i.volid]), None)
        if not appliance:
            msg = f"Appliance containing '{filename}' not found."
            raise ValueError(msg)
        return appliance

    def template_exists(self, template: str) -> bool:
        """Check if an appliance template exists in the stored appliances."""
        return bool(next(iter([i for i in self.root if template in i.volid]), None))


class StoredImage(BaseModel):
    """Represents a stored VM image in Proxmox storage."""

    volid: str
    size: int
    format: str
    ctime: int

    @property
    def image_name(self) -> str:
        """Get the image name from the volume ID by extracting the part after 'import/'."""
        return self.volid.split("import/")[-1]

    @property
    def storage(self) -> str:
        """Get the storage identifier from the volume ID."""
        return self.volid.split(":vztmpl")[0]


class StoredImages(RootModel[list[StoredImage]]):
    """A list of stored appliances."""

    def __iter__(self) -> Iterator[StoredImage]:
        """Return an iterator over the stored images."""
        return iter(self.root)

    def get_image(self, filename: str) -> StoredImage:
        return next(iter([i for i in self.root if filename in i.volid]))

    def image_exists(self, image: str) -> bool:
        """Check if an appliance template exists in the stored image."""
        return bool(next(iter([i for i in self.root if i.image_name == image]), None))


class VolumeContentInfo(BaseModel):
    """Represents information about the content of a volume in Proxmox storage."""

    format: str
    path: str
    size: int
    used: int
