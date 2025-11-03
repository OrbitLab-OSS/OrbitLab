"""Schema definitions for LXC container manifests in OrbitLab."""

from typing import Self

from pydantic import Field, SecretStr, ValidationError, model_validator

from orbitlab.data_types import ManifestKind

from .base import BaseManifest, Metadata, Spec


class LXCMetadata(Metadata):
    node: str
    hostname: str
    os_template: str
    storage: str


class LXCSpec(Spec):
    networks: list
    password: SecretStr | None = None
    ssh_public_key: SecretStr | None = None
    memory: int = Field(default=512)
    swap: int = Field(default=512)

    @model_validator(mode="after")
    def check_authentication(self) -> Self:
        """Ensure that either 'password' or 'ssh_public_key' is provided for authentication.

        Raises:
            ValidationError: If neither 'password' nor 'ssh_public_key' is provided.
        """
        if not self.password and not self.ssh_public_key:
            msg = "Either 'password' and/or 'ssh_public_key' must be provided."
            raise ValidationError(msg)
        return self



class LXCManifest(BaseManifest[LXCMetadata, LXCSpec]):
    """Manifest schema for LXC containers in OrbitLab.

    Either `password` or `ssh_public_key` must be provided.

    Attributes:
        node (str): The node where the container will be deployed.
        hostname (str): The hostname of the container.
        os_template (str): The OS template to use for the container.
        storage (str): The storage backend for the container.
        net0 (str): Network configuration for the container.
        password (SecretStr | None): Optional password for authentication.
        ssh_public_key (SecretStr | None): Optional SSH public keys for authentication.
        memory (int): Amount of memory allocated to the container.
        swap (int): Amount of swap space allocated to the container.
    """
    kind=ManifestKind.LXC
