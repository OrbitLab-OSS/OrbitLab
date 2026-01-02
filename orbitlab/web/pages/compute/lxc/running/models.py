"""LXC Management Models."""

from pydantic import BaseModel


class CreateLXCForm(BaseModel):
    """Form model for creating LXC containers."""

    node: str
    appliance: str
    name: str
    rootfs: str
    disk_size: int
    cores: int
    memory: int
    swap: int
    password: str
    sector: str
    subnet: str
