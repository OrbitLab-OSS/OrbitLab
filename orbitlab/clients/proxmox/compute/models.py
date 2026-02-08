"""Proxmox Compute Client Models."""

import ipaddress
from typing import Literal

from pydantic import BaseModel, Field, RootModel, computed_field


class Asset(BaseModel):
    """Represents an asset from a software release."""

    name: str
    digest: str
    browser_download_url: str

    @computed_field
    @property
    def formatted_name(self) -> str:
        """Return a human-readable formatted name for the asset."""
        _, os_type, os_version, arch, _ = self.name.split("-")
        return f"{os_type.capitalize()} {os_version} ({arch})"

    @computed_field
    @property
    def build_date(self) -> str:
        """Return the build date extracted from the asset name."""
        _, _, _, _, build_date_and_filetype = self.name.split("-")
        build_date, _ = build_date_and_filetype.split(".")
        return build_date


class ReleasedImages(BaseModel):
    """Represents a collection of released image assets."""

    assets: list[Asset]

    def list_images(self) -> list[Asset]:
        """Return a dictionary mapping formatted image names to their original asset names."""
        return [asset for asset in self.assets if asset.name.endswith(".qcow2")]

    def get_asset(self, asset_name: str) -> Asset:
        """Return the asset object for the asset with the given name."""
        return next(iter(asset for asset in self.assets if asset.name == asset_name))


class IpAddress(BaseModel):
    """Represents an IP address with its type, prefix, and value."""

    address_type: Literal["inet", "inet6", "ipv4", "ipv6"] = Field(alias="ip-address-type")
    prefix: str | int
    address: str = Field(alias="ip-address")


class LXCInterface(BaseModel):
    """Represents a LXC network interface with hardware address, name, and associated IP addresses."""

    hwaddr: str
    name: str
    ip_addresses: list[IpAddress] = Field(alias="ip-addresses")

    def get_ipv4_interface(self) -> ipaddress.IPv4Interface | None:
        """Return the IPv4 interface object for the first IPv4 address found."""
        ip = next(iter(addr for addr in self.ip_addresses if addr.address_type == "inet"), None)
        if ip:
            return ipaddress.IPv4Interface(address=f"{ip.address}/{ip.prefix}")
        return None


class LXCInterfaces(RootModel[list[LXCInterface]]):
    """Represents a collection of LXC network interfaces."""

    def get_default_ipv4(self) -> ipaddress.IPv4Interface | None:
        """Return the IPv4 interface object for the default 'eth0' network interface."""
        interface = next(iter([interface for interface in self.root if interface.name == "eth0"]), None)
        if interface:
            return interface.get_ipv4_interface()
        return None


class VMInterface(BaseModel):
    """Represents a VM network interface with its name and associated IP addresses."""

    name: str
    ip_addresses: list[IpAddress] = Field(alias="ip-addresses")

    def get_ipv4_interface(self) -> ipaddress.IPv4Interface | None:
        """Return the IPv4 interface object for the first IPv4 address found."""
        ip = next(iter(addr for addr in self.ip_addresses if addr.address_type == "ipv4"), None)
        if ip:
            return ipaddress.IPv4Interface(address=f"{ip.address}/{ip.prefix}")
        return None


class VMInterfaces(BaseModel):
    """Represents a collection of VM network interfaces."""

    result: list[VMInterface]

    def get_default_ipv4(self) -> ipaddress.IPv4Interface | None:
        """Return the IPv4 interface object for the default 'eth0' network interface."""
        interface = next(iter([interface for interface in self.result if interface.name == "eth0"]), None)
        if interface:
            return interface.get_ipv4_interface()
        return None
