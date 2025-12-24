"""Base schema definitions for OrbitLab manifest files."""

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Generic, TypeVar

import yaml
from pydantic import BaseModel, Field

from orbitlab.constants import Directories
from orbitlab.data_types import ManifestKind
from orbitlab.manifest.exceptions import ManifestNotFoundError

from .ref import Ref
from .serialization import SerializeEnum


class Tag(BaseModel):
    """A tag consisting of a name and value for OrbitLab manifest metadata."""

    name: str
    value: str


class Metadata(BaseModel):
    """Base metadata schema for OrbitLab manifest files."""

    tags: list[Tag] | None = Field(default=None)


class Spec(BaseModel):
    """Base specification schema for OrbitLab manifest files."""


MetaType = TypeVar("MetaType", bound=Metadata)
SpecType = TypeVar("SpecType", bound=Spec)
type ResolvedRefs = BaseManifest | Mapping[str, BaseManifest] | list[BaseManifest]
T = TypeVar("T", bound="BaseManifest")

class BaseManifest(BaseModel, Generic[MetaType, SpecType]):
    """Base class for OrbitLab manifest files."""

    kind: Annotated[ManifestKind, SerializeEnum]
    name: str
    metadata: MetaType
    spec: SpecType

    @property
    def _manifest_path(self) -> Path:
        """Return the file path of the manifest based on its kind and name."""
        return Directories.MANIFEST_ROOT / self.kind.value / f"{self.name}.yaml"

    def to_ref(self) -> Ref:
        """Create a reference to this manifest."""
        return Ref.create(kind=self.kind, name=self.name)

    @classmethod
    def load(cls: type[T], name: str) -> T:
        """Load a manifest from a YAML file by name."""
        path = Directories.MANIFEST_ROOT / cls.model_fields["kind"].default / f"{name}.yaml"
        if not path.exists():
            raise ManifestNotFoundError(name=name, kind=cls.kind)

        with path.open("r", encoding="utf-8") as f:
            return cls.model_validate(yaml.safe_load(f))

    def save(self) -> None:
        """Save the manifest to its YAML file on disk."""
        self._manifest_path.parent.mkdir(exist_ok=True)
        data: dict[str, Any] = self.model_dump(exclude_none=True, by_alias=True)
        with self._manifest_path.open("wt", encoding="utf-8") as stream:
            yaml.safe_dump(data=data, stream=stream, sort_keys=False)

    def delete(self) -> None:
        """Delete the manifest file from disk."""
        self._manifest_path.unlink(missing_ok=True)

    @classmethod
    def get_existing(cls) -> list[str]:
        """Return a list of manifest names based on their kind."""
        path = Directories.MANIFEST_ROOT / cls.model_fields["kind"].default
        return [p.stem for p in path.glob("*.yaml")]
