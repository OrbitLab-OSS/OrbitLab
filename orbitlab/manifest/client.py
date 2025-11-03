"""Client for handling OrbitLab manifest files in the Proxmox Cluster Filesystem.

Provides functionality to list, load, save, and delete manifest files using YAML serialization.
"""

from pathlib import Path
from typing import TypeVar

import yaml

from orbitlab.constants import MANIFEST_ROOT
from orbitlab.data_types import ManifestKind

from .exceptions import ManifestNotFoundError, ManifestWriteError
from .schemas.base import BaseManifest

T = TypeVar("T", bound=BaseManifest)

class ManifestClient:
    """Handles loading and saving OrbitLab manifests stored in the Proxmox Cluster Filesystem."""

    def __init__(self) -> None:
        """Initialize the ManifestClient and ensure the manifest root directory exists."""
        MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)

    def list_manifests(self) -> list[str]:
        """Return all manifest filenames (without extension)."""
        return [p.stem for p in MANIFEST_ROOT.glob("**/*.yaml")]

    def load(self, name: str, kind: ManifestKind, model: type[T]) -> T:
        """Load a manifest file of a given kind and validate it against the provided model.

        Args:
            name (str): The name of the manifest to load.
            kind (ManifestKind): The kind/category of the manifest.
            model (type[BaseManifest]): The model class to validate the manifest data against.

        Raises:
            ManifestNotFoundError: If the manifest file does not exist.

        Returns:
            An instance of the model populated with the manifest data.
        """
        path = MANIFEST_ROOT / kind.value / f"{name}.yaml"
        if not path.exists():
            raise ManifestNotFoundError(name=name, kind=kind)

        with path.open("r", encoding="utf-8") as f:
             return model.model_validate(yaml.safe_load(f))

    def save(self, manifest: BaseManifest, *, overwrite: bool = True) -> None:
        """Save a manifest file to disk.

        Args:
            manifest (BaseManifest): The manifest instance to save.
            overwrite (bool, optional): Whether to overwrite the file if it exists. Defaults to True.

        Raises:
            ManifestWriteError: If the file exists and overwrite is False.
        """
        if manifest.manifest_path.exists() and not overwrite:
            raise ManifestWriteError(manifest=manifest, reason="No overwrite permissions.")

        manifest.manifest_path.parent.mkdir(parents=True, exist_ok=True)

        with manifest.manifest_path.open("wt", encoding="utf-8") as f:
            yaml.safe_dump(manifest.model_dump(exclude_none=True, by_alias=True), f, sort_keys=False)

    def delete(self, manifest: BaseManifest) -> None:
        """Delete the manifest file from disk if it exists.

        Args:
            manifest (BaseManifest): The manifest instance whose file should be deleted.
        """
        if manifest.manifest_path.exists():
            manifest.manifest_path.unlink()

    def get_existing_by_kind(self, kind: ManifestKind) -> dict[str, Path]:
        """Return a dictionary mapping manifest names to their file paths for a given kind.

        Args:
            kind (ManifestKind): The kind/category of the manifests to list.

        Returns:
            dict[str, Path]: A mapping from manifest name (without extension) to its Path.
        """
        path = MANIFEST_ROOT / kind.value
        return {p.stem: p for p in path.glob("*.yaml")}
