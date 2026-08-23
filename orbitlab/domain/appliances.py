"""Validated appliance inputs kept independent from both NiceGUI and Proxmox."""

from __future__ import annotations

from dataclasses import dataclass
import base64
from ipaddress import IPv4Network
import json


@dataclass(frozen=True, slots=True)
class ApplianceNetworkProfile:
    """The minimal network capabilities needed to provision one appliance."""

    appliance: str
    nic_count: int
    supports_dhcp: bool
    requires_guest_agent: bool
    minimum_mtu: int = 1280

    def validate(self, *, network: str, mtu: int, nic_count: int, dhcp_enabled: bool, guest_agent: bool) -> None:
        """Raise a concise operator-facing error before a provisioning event is queued."""
        parsed_network = IPv4Network(network, strict=False)
        if nic_count != self.nic_count:
            raise ValueError(f"{self.appliance} requires exactly {self.nic_count} network interface(s).")
        if mtu < self.minimum_mtu:
            raise ValueError(f"{self.appliance} requires an MTU of at least {self.minimum_mtu}.")
        if self.supports_dhcp and not dhcp_enabled:
            raise ValueError(f"{self.appliance} requires DHCP during bootstrap.")
        if self.requires_guest_agent and not guest_agent:
            raise ValueError(f"{self.appliance} requires the Proxmox guest agent.")
        if parsed_network.num_addresses < 8:
            raise ValueError("The selected network is too small for an OrbitLab appliance.")


@dataclass(frozen=True, slots=True)
class BootstrapDocument:
    """Structured bootstrap payload transported as base64 JSON, never shell syntax."""

    kind: str
    resource_id: str
    values: dict[str, str | int | bool | list[str]]

    def encode(self) -> str:
        """Return the stable base64 JSON form accepted by appliance bootstrap tools."""
        document = {"kind": self.kind, "resource_id": self.resource_id, "values": self.values}
        encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        return base64.b64encode(encoded).decode()
