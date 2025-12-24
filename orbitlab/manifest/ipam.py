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
    vmid: str | int
    allocated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Subnet(BaseModel):
    """A subnet configuration for IP address management."""

    cidr_block: Annotated[IPv4Network, SerializeIP]
    name: str
    assignments: Annotated[list[IPAssignment], Field(default_factory=list)]

    def get_assignment(self, vmid: str) -> IPAssignment | None:
        """Get the IP assignment for a specific VM ID."""
        return next(iter(assignment for assignment in self.assignments if str(assignment.vmid) == vmid), None)

    def get_next_available_ip(self) -> IPv4Interface:
        """Get the next available IP address in the subnet."""
        assigned = [assigned.address.ip for assigned in self.assignments]
        hosts = list(self.cidr_block.hosts())
        usable = hosts[NetworkSettings.RESERVED_USABLE_IPS:]
        for ip in usable:
            if ip not in assigned:
                return IPv4Interface(f"{ip}/{self.cidr_block.prefixlen}")
        raise ValueError


class IpamSpec(Spec):
    """Specification for IPAM (IP Address Management) configuration."""

    subnets: list[Subnet]


class IpamManifest(BaseManifest[IpamMetadata, IpamSpec]):
    """Manifest for IPAM (IP Address Management) configuration."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.IPAM

    def get_subnet(self, name: str) -> Subnet | None:
        """Get a subnet by name from the IPAM specification."""
        return next((subnet for subnet in self.spec.subnets if subnet.name == name), None)

    def find_ip(self, vmid: str) -> str:
        """Find the IP address assigned to a VM across all subnets."""
        for subnet in self.spec.subnets:
            if assignment := subnet.get_assignment(vmid=vmid):
                return str(assignment.address)
        return ""

    def get_assigned_ip(self, subnet_name: str, vmid: str) -> IPv4Interface | None:
        """Get the IPv4 assignment for the VMID or return None."""
        subnet = self.get_subnet(name=subnet_name)
        if not subnet:
            return None
        return next(iter(assigned.address for assigned in subnet.assignments if assigned.vmid == vmid), None)

    def assign_ip(self, subnet_name: str, vmid: str) -> IPv4Interface:
        """Assign an IP address to a VM."""
        subnet = self.get_subnet(name=subnet_name)
        if subnet:
            address = subnet.get_next_available_ip()
            subnet.assignments.append(IPAssignment(address=address, vmid=vmid))
            self.save()
            return address
        raise ValueError

    def release_ip(self, subnet_name: str, ip: IPv4Interface) -> None:
        """Release an IP address assignment."""
        subnet = self.get_subnet(name=subnet_name)
        if subnet:
            subnet.assignments = [assigned for assigned in subnet.assignments if assigned.address != ip]
            self.save()
