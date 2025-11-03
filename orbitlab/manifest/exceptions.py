"""Manifest Client Exceptions."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schemas.base import BaseManifest, ManifestKind


class ManifestNotFoundError(Exception):
    """Exception raised when a manifest of a specified name and kind is not found."""

    def __init__(self, name: str, kind: "ManifestKind") -> None:
        """Initialize ManifestNotFoundError with manifest name and kind.

        Args:
            name (str): The name of the manifest.
            kind (ManifestKind): The kind of the manifest.
        """
        super().__init__(f"Manifest {name} of kind {kind} not found.")
        self.name = name
        self.kind = kind


class ManifestWriteError(Exception):
    """Exception raised when a manifest cannot be written due to a specific reason."""

    def __init__(self, manifest: "BaseManifest", reason: str) -> None:
        """Initialize ManifestWriteError with manifest and reason.

        Args:
            manifest (BaseManifest): The manifest that could not be written.
            reason (str): The reason why writing failed.
        """
        super().__init__(f"Unable to write manifest {manifest.name} of kind {manifest.kind}: {reason}")
        self.manifest = manifest
        self.reason = reason


class ManifestRegistrationError(Exception):
    """Exception raised when there is an error registering a manifest of a specific kind."""

    def __init__(self, kind: "ManifestKind", msg: str) -> None:
        """Initialize ManifestRegistrationError with manifest kind and error message.

        Args:
            kind (ManifestKind): The kind of the manifest.
            msg (str): The error message describing the registration failure.
        """
        super().__init__(f"{kind}: {msg}")
        self.kind = kind
        self.msg = msg
