"""Proxmox Appliances Client Models."""

from collections.abc import Iterator
from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel

from orbitlab.manifest.serialization import PveBool


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


class Asset(BaseModel):
    """Represents an asset from a software release."""

    name: str
    content_type: Literal["application/gzip", "application/octet-stream"]
    digest: str
    browser_download_url: str


class LatestRelease(BaseModel):
    """Represents the latest release information from a repository."""

    name: str
    tag_name: str
    assets: list[Asset]

    @property
    def version(self) -> str:
        """Get the version string by removing the 'v' prefix from tag_name."""
        return self.tag_name.replace("v", "")

    def get_appliance_asset(self) -> Asset:
        """Get the appliance asset with gzip content type from the release assets."""
        return next(asset for asset in self.assets if asset.content_type == "application/gzip")


class StoredAppliance(BaseModel):
    """Represents a stored appliance template in Proxmox storage."""

    volid: str
    size: int
    format: str
    ctime: int

    @property
    def is_orbitlab_appliance(self) -> bool:
        """Check if this is an OrbitLab appliance based on the volume ID."""
        if "sector-gateway-" in self.volid:
            return True
        if "backplane-dns-" in self.volid:
            return True
        return "sector-dns-" in self.volid

    @property
    def template(self) -> str:
        """Get the template name from the volume ID by extracting the part after 'vztmpl/'."""
        return self.volid.split("vztmpl/")[-1]

    @property
    def storage(self) -> str:
        """Get the storage identifier from the volume ID."""
        return self.volid.split(":vztmpl")[0]


class StoredAppliances(RootModel[list[StoredAppliance]]):
    """A list of stored appliances."""

    def __iter__(self) -> Iterator[StoredAppliance]:
        """Return an iterator over the stored appliances."""
        return iter([i for i in self.root if not i.is_orbitlab_appliance])


class AgentExecStatus(BaseModel):
    """Represents the execution status of an agent command in Proxmox."""

    exited: PveBool
    stderr: str = Field(alias="err-data", default="")
    stdout: str = Field(alias="out-data", default="")
    exitcode: int | None = None
    signal: int | None = None

    @property
    def logs(self) -> list[str]:
        """Return combined non-empty lines from stdout and stderr as a list of log entries."""
        formatted_logs = [line for line in self.stdout.split("\n") if line]
        formatted_logs.extend([line for line in self.stderr.split("\n") if line])
        return formatted_logs

class VolumeContentInfo(BaseModel):
    """Represents information about the content of a volume in Proxmox storage."""

    format: str
    path: str
    size: int
    used: int


class AgentExecPid(BaseModel):
    """Represents the process ID of an agent execution in Proxmox."""

    pid: int
