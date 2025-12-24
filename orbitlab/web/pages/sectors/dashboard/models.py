"""OrbitLab Networks Dashboard Models."""

import ipaddress

from pydantic import BaseModel, computed_field

from orbitlab.constants import NetworkSettings
from orbitlab.data_types import SectorState
from orbitlab.manifest.ipam import IpamManifest
from orbitlab.manifest.sector import SectorManifest


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


class CreateSectorForm(BaseModel):
    """Form model for creating a new sector."""

    tag: int
    name: str
    cidr_block: str
    subnets: list[dict]

    @property
    def sector_id(self) -> str:
        """Generate the sector ID based on the network tag."""
        return f"olvn{self.tag}"

    def create_sector_manifest(self) -> SectorManifest:
        """Create the sector manifest."""
        ipam = self.__create_ipam__()
        manifest = SectorManifest.model_validate({
            "name": self.sector_id,
            "metadata": {
                "alias": self.name,
                "tag": self.tag,
                "state": SectorState.PENDING,
            },
            "spec": {
                "cidr_block": self.cidr_block,
                "ipam": ipam.to_ref(),
                "subnets": self.subnets,
            },
        })
        manifest.save()
        return manifest

    def __create_ipam__(self) -> IpamManifest:
        """Create an IPAM manifest from the network form data."""
        manifest = IpamManifest.model_validate({
            "name": f"ipam-{self.sector_id}",
            "metadata": {
                "name": self.name,
                "sector_name": self.name,
                "sector_id": self.sector_id,
            },
            "spec": {
                "subnets": self.subnets,
            },
        })
        manifest.save()
        return manifest
