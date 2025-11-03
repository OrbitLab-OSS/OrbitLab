"""Schema definitions for SDN configuration manifests.

This module defines Pydantic models for SDN metadata, DHCP ranges, subnets, and manifest specifications.
"""

import ipaddress
from typing import Annotated

from pydantic import BaseModel

from orbitlab.data_types import ManifestKind, ZoneTypes

from .base import BaseManifest, Metadata, Spec
from .serialization import SerializeEnum, SerializeIP


class SDNMetadata(Metadata):
    """Metadata for SDN configuration."""
    zone_type: Annotated[ZoneTypes, SerializeEnum]
    zone_name: str
    mac: str
    controller: str | None = None


class DHCPRange(BaseModel):
    """Represents a DHCP IP address range with a start and end address."""
    start: Annotated[ipaddress.IPv4Address, SerializeIP]
    end: Annotated[ipaddress.IPv4Address, SerializeIP]


class Subnet(BaseModel):
    """Represents a network subnet with DNS prefix, gateway, CIDR block, and DHCP ranges."""
    dns_prefix: str
    gateway: Annotated[ipaddress.IPv4Address, SerializeIP]
    cidr_block: Annotated[ipaddress.IPv4Network, SerializeIP]
    dhcp_ranges: list[DHCPRange]


class SDNSpec(Spec):
    """Specification for SDN configuration, including subnets and MTU.

    Attributes:
        subnets (list[Subnet]): List of network subnets.
        mtu (int): Maximum Transmission Unit size.
    """
    subnets: list[Subnet]
    mtu: int


class SDNManifest(BaseManifest[SDNMetadata, SDNSpec]):
    """Manifest for SDN configuration, specifying metadata and specification details.

    Attributes:
        kind (ManifestKind): The kind of manifest, set to SDN.
    """
    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.SDN
