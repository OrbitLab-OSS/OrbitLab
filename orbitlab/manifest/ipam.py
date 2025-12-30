"""OrbitLab IPAM Manifest."""

from datetime import UTC, datetime
from ipaddress import IPv4Interface, IPv4Network
from typing import Annotated

from pydantic import BaseModel, Field

from orbitlab.constants import NetworkSettings
from orbitlab.data_types import ManifestKind

from .base import BaseManifest, Metadata, Spec
from .serialization import SerializeEnum, SerializeIP


class IpamMetadata(Metadata):
    """Metadata for IPAM (IP Address Management) configuration."""

    sector_name: str
    sector_id: str


class IPAssignment(BaseModel):
    """An IP address assignment to a virtual machine or LXC."""

    address: Annotated[IPv4Interface, SerializeIP]
    is_vip: bool = False
    allocated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Subnet(BaseModel):
    """A subnet configuration for IP address management."""

    cidr_block: Annotated[IPv4Network, SerializeIP]
    name: str
    assignments: dict[int, IPAssignment] = Field(default_factory=dict)

    def get_next_available_ip(self) -> IPv4Interface:
        """Get the next available IP address in the subnet."""
        assigned = [assigned.address.ip for assigned in self.assignments.values()]
        hosts = list(self.cidr_block.hosts())
        usable = hosts[NetworkSettings.RESERVED_USABLE_IPS:]
        for ip in usable:
            if ip not in assigned:
                return IPv4Interface(f"{ip}/{self.cidr_block.prefixlen}")
        raise ValueError

    def available_ips(self) -> int:
        """Return the number of available IP addresses in the subnet."""
        return len(list(self.cidr_block.hosts())) - NetworkSettings.RESERVED_USABLE_IPS - len(self.assignments)


class IpamSpec(Spec):
    """Specification for IPAM (IP Address Management) configuration."""

    subnets: list[Subnet]


class IpamManifest(BaseManifest[IpamMetadata, IpamSpec]):
    """Manifest for IPAM (IP Address Management) configuration."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.IPAM

    def get_subnet(self, name: str) -> Subnet:
        """Get a subnet by name from the IPAM specification."""
        return next(subnet for subnet in self.spec.subnets if subnet.name == name)

    def find_ip(self, vmid: int) -> str:
        """Find the IP address assigned to a VM across all subnets."""
        for subnet in self.spec.subnets:
            if assignment := subnet.assignments.get(vmid):
                return str(assignment.address)
        return ""

    def get_assigned_ip(self, subnet_name: str, vmid: int) -> IPv4Interface | None:
        """Get the IPv4 assignment for the VMID or return None."""
        subnet = self.get_subnet(name=subnet_name)
        if not subnet:
            return None
        if assignment := subnet.assignments.get(vmid):
            return assignment.address
        return None

    def assign_ip(self, subnet_name: str, vmid: int) -> IPv4Interface:
        """Assign an IP address to a VM."""
        subnet = self.get_subnet(name=subnet_name)
        if subnet:
            address = subnet.get_next_available_ip()
            subnet.assignments[vmid] = IPAssignment(address=address)
            self.save()
            return address
        raise ValueError

    def release_ip(self, subnet_name: str, vmid: int) -> None:
        """Release an IP address assignment."""
        subnet = self.get_subnet(name=subnet_name)
        if vmid in subnet.assignments:
            del subnet.assignments[vmid]
            self.save()
