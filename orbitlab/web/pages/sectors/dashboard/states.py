"""OrbitLab Networks Dashboard States."""

import re
from ipaddress import IPv4Network

import reflex as rx

from orbitlab.clients.proxmox.appliances import ProxmoxAppliances
from orbitlab.clients.proxmox.networks import AttachedInstances
from orbitlab.data_types import OrbitLabApplianceType
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.web.states.utilities import CacheBuster

from .models import SectorSpec


class CreateSectorDialogState(rx.State):
    """Create Sector Dialog State."""

    form_data: rx.Field[dict] = rx.field(default_factory=dict)
    cidr_block: rx.Field[str] = rx.field(default="")
    subnet_count: rx.Field[int] = rx.field(default=2)

    @rx.var
    def sector_specs(self) -> list[SectorSpec]:
        """Generate network specifications by subnet-ing the CIDR block."""
        if self.cidr_block:
            network = IPv4Network(self.cidr_block)
            subnet_bits = (self.subnet_count - 1).bit_length()
            new_prefix = network.prefixlen + subnet_bits
            return [
                SectorSpec(cidr_block=str(cidr_block))
                for cidr_block in list(network.subnets(new_prefix=new_prefix))[:self.subnet_count]
            ]
        return []


class DeleteSectorDialogState(rx.State):
    """Delete Sector Dialog State."""

    sector_id: rx.Field[str] = rx.field(default="")
    attached_vms: rx.Field[list[AttachedInstances]] = rx.field(default_factory=list)
    confirmation: rx.Field[str] = rx.field(default="")

    @rx.var
    def has_attached_compute(self) -> bool:
        """Check if there are any attached VMs to this sector."""
        return bool(self.attached_vms)

    @rx.var
    def delete_disabled(self) -> bool:
        """Check if the delete button should be disabled."""
        return self.confirmation != self.sector_id


class SectorAppliancesTableState(CacheBuster, rx.State):
    """Sector Appliances Table State."""

    @rx.var(deps=["_cached_gateway_appliance"])
    def gateway_appliance(self) -> str:
        """Get the gateway appliance name from the cluster manifest."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        return cluster_manifest.metadata.gateway_appliance

    @rx.var
    def downloaded_gateway_version(self) -> str:
        """Extract the version number from the downloaded gateway appliance filename."""
        if match := re.match(r"sector-gateway-(\d+\.\d+\.\d).tar.gz", self.gateway_appliance):
            return match.groups()[0]
        return "Err"

    @rx.var
    def latest_gateway_version(self) -> str:
        """Get the latest gateway appliance version from Proxmox."""
        latest = ProxmoxAppliances().get_latest_release(appliance_type=OrbitLabApplianceType.SECTOR_GATEWAY)
        return latest.version
