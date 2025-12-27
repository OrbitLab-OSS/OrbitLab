"""Schema definitions for LXC container manifests in OrbitLab."""

from typing import Self

from pydantic import Field, SecretStr, ValidationError, model_validator

from orbitlab.data_types import ManifestKind

from .base import BaseManifest, Metadata, Spec


class LXCMetadata(Metadata):
    """Metadata schema for LXC containers."""

    node: str
    hostname: str
    os_template: str
    storage: str


class LXCSpec(Spec):
    """Specification schema for LXC containers."""

    networks: list
    password: SecretStr | None = None
    ssh_public_key: SecretStr | None = None
    memory: int = Field(default=512)
    swap: int = Field(default=512)

    @model_validator(mode="after")
    def check_authentication(self) -> Self:
        """Ensure that either 'password' or 'ssh_public_key' is provided for authentication."""
        if not self.password and not self.ssh_public_key:
            msg = "Either 'password' and/or 'ssh_public_key' must be provided."
            raise ValidationError(msg)
        return self


class LXCManifest(BaseManifest[LXCMetadata, LXCSpec]):
    """Manifest schema for LXC containers in OrbitLab."""

    kind: ManifestKind = ManifestKind.LXC
