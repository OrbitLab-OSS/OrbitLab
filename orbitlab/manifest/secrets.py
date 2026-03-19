"""Manifest schemas for secrets."""  # noqa: A005

from pathlib import Path
from typing import Annotated, Self

from pydantic import Field

from orbitlab.data_types import ManifestKind
from orbitlab.services.vault.client import SecretVault

from .base import BaseManifest, Metadata, Spec
from .serialization import SerializeEnum


class SecretSpec(Spec):
    """Specification for a secret."""

    secret_name: str
    version: int = Field(ge=1)
    previous_versions: list[int] = Field(default_factory=list)


class SecretMetadata(Metadata):
    """Metadata for a secret, including an optional description."""

    description: str = Field(default="")


class SecretManifest(BaseManifest[SecretMetadata, SecretSpec]):
    """Manifest class for storing secret metadata and specification."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.SECRET

    @classmethod
    def create(cls, secret_name: str, secret_value: str, description: str) -> Self:
        version = SecretVault().create(secret_name=Path(secret_name), value=secret_value)
        manifest = cls(
            name=secret_name.replace("/", "."),
            metadata=SecretMetadata(description=description),
            spec=SecretSpec(secret_name=secret_name, version=version),
        )
        manifest.save()
        return manifest

    @classmethod
    def create_lxc_password(cls, lxc_id: str, password: str) -> Self:
        """Create and store a password for an LXC container in the secret vault."""
        secret_name = f"/orbitlab/lxc/{lxc_id}"
        return cls.create(secret_name=secret_name, secret_value=password, description=f"Password for LXC {lxc_id}")

    @classmethod
    def create_vm_password(cls, vm_id: str, password: str) -> Self:
        """Create and store a password for a VM in the secret vault."""
        secret_name = f"/orbitlab/vm/{vm_id}"
        return cls.create(secret_name=secret_name, secret_value=password, description=f"Password for VM {vm_id}")

    @classmethod
    def create_service_secret(cls, service_name: str, service_id: str, *, value: str = "", subservice_name: str = "") -> Self:
        """Create and store a random secret for a service in the secret vault."""
        secret_name = f"/orbitlab/{service_name}/{service_id}"
        if subservice_name:
            secret_name += f"/{subservice_name}"
        return cls.create(
            secret_name=secret_name,
            secret_value=value or SecretVault.generate_random_password(),
            description=f"{service_name} secret for {service_id}",
        )

    @classmethod
    def store_private_key(cls, secret_name: Path, key_data: str) -> Self:
        """Create and store a private key in the secret vault."""
        manifest_name = str(secret_name).replace("/", ".")
        if manifest_name in SecretManifest.get_existing():
            manifest = SecretManifest.load(name=manifest_name)
            manifest.spec.version = SecretVault().update(
                secret_name=secret_name, version=manifest.spec.version, value=key_data,
            )
        else:
            version = SecretVault().create(secret_name=secret_name, value=key_data)
            manifest = cls(
                name=manifest_name,
                metadata=SecretMetadata(),
                spec=SecretSpec(secret_name=str(secret_name), version=version),
            )
        manifest.save()
        return manifest

    @classmethod
    def load_from_name(cls, secret_name: Path | str) -> Self:
        name = str(secret_name).replace("/", ".")
        return cls.load(name=name)

    def get_current_value(self) -> str:
        """Get the current value of the secret from the vault."""
        return (
            SecretVault()
            .get(
                secret_name=self.spec.secret_name,
                version=self.spec.version,
            )
            .secret_string.get_secret_value()
        )

    def delete(self) -> None:
        """Delete the secret from the vault and remove the manifest."""
        SecretVault().delete(secret_name=Path(self.spec.secret_name))
        return super().delete()
