"""Proxmox Compute Client Models."""

import ipaddress
from typing import Literal, Self

from pydantic import BaseModel, Field, RootModel, computed_field


class VendoredImage(BaseModel):
    """Represents an asset from a software release."""

    filename: str
    digest: str
    size: int
    browser_download_url: str

    @computed_field
    @property
    def formatted_name(self) -> str:
        """Return a human-readable formatted name for the asset."""
        os_type, os_version, arch, _ = self.filename.split("-")
        return f"{os_type.capitalize()} {os_version} {arch}"

    @computed_field
    @property
    def build_date(self) -> str:
        """Return the build date extracted from the asset name."""
        _, _, _, build_date_and_filetype = self.filename.split("-")
        build_date, _ = build_date_and_filetype.split(".")
        return build_date

    @property
    def checksum(self) -> str:
        _, checksum = self.digest.split(":")
        return checksum

    @property
    def checksum_algorithm(self) -> str:
        checksum_algorithm, _ = self.digest.split(":")
        return checksum_algorithm


class VendoredImages(BaseModel):
    """Represents a collection of released image assets."""

    images: list[VendoredImage]

    def get_os_image(self, os: str) -> VendoredImage:
        """Return the asset object for the OS image with the given formatted name."""
        return next(iter(img for img in self.images if img.formatted_name == os))


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


class InstanceStatus(BaseModel):
    """Represents the status of a compute instance."""

    status: Literal["stopped", "running"]
    vmid: int
    name: str


class VMVolume(BaseModel):
    volume_id: str
    size: str

    @classmethod
    def from_config_string(cls, value: str) -> Self:
        storage, extra = value.split(":")
        disk, size = extra.split(",")
        _, disk_name = disk.split("/")
        return cls(
            storage=storage,
            disk_name=disk_name,
            size=size.replace("size=", "")
        )


class ProxmoxPool(BaseModel):
    pool_id: str = Field(alias="poolid")
    comment: str


class ProxmoxPools(RootModel[list[ProxmoxPool]]):
    
    def get_pool_by_alias(self, alias: str) -> ProxmoxPool | None:
        return next(iter([pool for pool in self.root if pool.comment == alias]), None)

    def get_pool_by_id(self, pool_id: str) -> ProxmoxPool | None:
        return next(iter([pool for pool in self.root if pool.pool_id == pool_id]), None)
