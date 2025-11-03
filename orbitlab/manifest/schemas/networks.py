"""Schema definitions for Proxmox network bridge configurations.

This module provides Pydantic models and type annotations for representing
network bridge settings, including IPv4/IPv6 configuration, interface types,
and serialization helpers.
"""

import ipaddress
from typing import Annotated

from pydantic import BaseModel, Field

from orbitlab.data_types import NetworkMethods, NetworkTypes

from .serialization import SerializeEnum, SerializeIP


class BridgeNetworks(BaseModel):
    """Represents a network bridge configuration for a Proxmox cluster node.

    Attributes:
        active (bool): Whether the bridge is currently active.
        autostart (bool): Whether the bridge is set to autostart.
        interface_type (NetworkTypes): The type of network interface (aliased as "type").
        interface_name (str): The name of the network interface (aliased as "iface").
        physical_interface (bool): Whether the physical interface exists (aliased as "exists").
        ipv4_method (NetworkMethods): The IPv4 configuration method (aliased as "method").
        ipv4_address (ipaddress.IPv4Address): The IPv4 address assigned to the bridge (aliased as "address").
        ipv6_method (NetworkMethods): The IPv6 configuration method (aliased as "method6").
        ipv6_address (ipaddress.IPv4Address | None): The IPv6 address assigned to the bridge (aliased as "address6").
        cidr (ipaddress.IPv4Network | None): The CIDR network for the bridge.
        gateway (ipaddress.IPv4Address): The gateway address for the bridge.
        ports (list[str] | None): The list of ports associated with the bridge.
    """
    active: bool
    autostart: bool
    interface_type: Annotated[NetworkTypes, SerializeEnum]
    interface_name: str
    physical_interface: bool
    ipv4_method: Annotated[NetworkMethods, SerializeEnum]
    ipv4_address: Annotated[ipaddress.IPv4Address, SerializeIP]
    ipv6_method: Annotated[NetworkMethods, SerializeEnum]
    ipv6_address: Annotated[ipaddress.IPv4Address | None, SerializeIP, Field(default=None)]
    cidr: Annotated[ipaddress.IPv4Interface | None, SerializeIP, Field(default=None)]
    gateway: Annotated[ipaddress.IPv4Address | None, SerializeIP, Field(default=None)]
