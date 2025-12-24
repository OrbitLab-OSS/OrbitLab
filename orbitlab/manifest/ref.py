"""OrbitLab Manifest Reference."""

from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, model_validator

from orbitlab.constants import Directories
from orbitlab.data_types import ManifestKind
from orbitlab.manifest.exceptions import ManifestNotFoundError


class Ref(BaseModel):
    """A reference to another manifest, used for linking manifests by reference.

    Attributes:
        ref (str): The reference string in the format 'kind/filename.yaml'.
        _kind (Kind | None): The kind of the referenced manifest.
        _name (str): The name of the referenced manifest.
    """

    ref: str
    kind: ManifestKind | None = Field(default=None, exclude=True)
    name: str = Field(default="", exclude=True)

    @property
    def _manifest_ref_path(self) -> Path:
        if self.kind:
            return Directories.MANIFEST_ROOT / self.kind.value / f"{self.name}.yaml"
        raise ValueError

    @model_validator(mode="after")
    def validate_ref(self) -> Self:
        """Validate the reference string, set the kind and filename, and check if the manifest file exists."""
        kind, filename = self.ref.split("/")
        self.kind = ManifestKind(kind)
        self.name = filename.split(".yaml")[0]
        if not self._manifest_ref_path.exists():
            raise ManifestNotFoundError(name=self.name, kind=self.kind)
        return self

    @classmethod
    def create(cls, kind: ManifestKind, name: str) -> "Ref":
        """Create a Ref instance from kind and name components."""
        return cls.model_validate({"ref": f"{kind.value}/{name}.yaml"})
