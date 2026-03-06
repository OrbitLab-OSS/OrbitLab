"""LXC Management Models."""

from typing import Self

from pydantic import BaseModel, model_validator

from orbitlab.services import SecretVault


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

    @model_validator(mode="after")
    def ensure_password(self) -> Self:
        if not self.password:
            self.password = SecretVault.generate_random_password()
        return self
