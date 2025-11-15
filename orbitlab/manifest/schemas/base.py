"""Base schema definitions for OrbitLab manifest files."""

from pathlib import Path
from types import UnionType
from typing import Annotated, Generic, Self, TypeVar, get_type_hints

import yaml
from pydantic import (
    BaseModel,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from orbitlab.constants import MANIFEST_ROOT
from orbitlab.data_types import ManifestKind
from orbitlab.manifest.exceptions import ManifestNotFoundError, ManifestRegistrationError
from orbitlab.manifest.schemas.serialization import SerializeEnum


class Tag(BaseModel):
    """A tag consisting of a name and value for OrbitLab manifest metadata."""

    name: str
    value: str


class Metadata(BaseModel):
    """Base metadata schema for OrbitLab manifest files."""

    tags: Annotated[list[Tag] | None, Field(default=None)]


class Spec(BaseModel):
    """Base specification schema for OrbitLab manifest files."""


MetaType = TypeVar("MetaType", bound=Metadata)
SpecType = TypeVar("SpecType", bound=Spec)


class Ref(BaseModel, Generic[SpecType]):
    """A reference to another manifest, used for linking manifests by reference.

    Attributes:
        ref (str): The reference string in the format 'kind/filename.yaml'.
        _kind (Kind | None): The kind of the referenced manifest.
        _name (str): The name of the referenced manifest.
    """

    ref: str
    _kind: ManifestKind | None = None
    _name: str = ""

    @property
    def _manifest_ref_path(self) -> Path:
        return MANIFEST_ROOT / self._kind.value / f"{self._name}.yaml"

    @model_validator(mode="after")
    def validate_ref(self) -> Self:
        """Validate the reference string, set the kind and filename, and check if the manifest file exists.

        Raises:
            ManifestNotFoundError: If the referenced manifest file does not exist.
        """
        kind, filename = self.ref.split("/")
        self._kind = ManifestKind(kind)
        self._name = filename.split(".yaml")[0]
        if not self._manifest_ref_path.exists():
            raise ManifestNotFoundError(name=self._name, kind=self._kind)
        return self

    def resolve_ref(self, registry: dict[str, type["BaseManifest"]]) -> "BaseManifest":
        """Resolve the referenced specification using the provided registry.

        Args:
            registry (dict[str, type["BaseManifest"]]): A mapping of manifest kinds to their corresponding classes.

        Returns:
            BaseManifest: The resolved manifest object.

        Raises:
            ManifestRegistrationError: If the manifest kind is not registered.
        """
        if self._kind.value not in registry:
            raise ManifestRegistrationError(kind=self._kind, msg="Never registered.")
        model = registry[self._kind.value]
        with self._manifest_ref_path.open("r", encoding="utf-8") as f:
            return model.model_validate(yaml.safe_load(f))


class BaseManifest(BaseModel, Generic[MetaType, SpecType]):
    """Base class for OrbitLab manifest files.

    Attributes:
        kind (ManifestKind): The kind of manifest.
        name (str): The name of the manifest.
    """

    kind: Annotated[ManifestKind, SerializeEnum]
    name: str
    metadata: MetaType
    spec: SpecType
    _registry: dict[str, type["BaseManifest"]] = {}

    def __init_subclass__(cls, **kwargs: dict) -> None:
        """Initialize subclass and register manifest kind."""
        if cls.__name__.startswith("BaseManifest"):
            # Ignore BaseManifest itself
            return
        if cls.kind.value in cls._registry.default:
            raise ManifestRegistrationError(kind=cls.kind, msg="Manifest already registered.")
        cls._registry.default[cls.kind.value] = cls
        super().__init_subclass__(**kwargs)

    @classmethod
    def get_manifest_model(cls, kind: ManifestKind) -> "BaseManifest":
        """Get the registered manifest model class for the specified kind.

        Args:
            kind (ManifestKind): The kind of manifest to retrieve.

        Returns:
            type["BaseManifest"]: The manifest class registered for the given kind.

        Raises:
            ManifestRegistrationError: If the manifest kind is not registered.
        """
        if kind.value not in cls._registry.default:
            raise ManifestRegistrationError(kind=kind, msg="Never registered.")
        return cls._registry.default[kind.value]

    @property
    def manifest_path(self) -> Path:
        """Return the file path of the manifest based on its kind and name."""
        return MANIFEST_ROOT / self.kind.value / f"{self.name}.yaml"

    @property
    def ref(self) -> dict[str, str]:
        """Return a dictionary reference to this manifest's kind and name."""
        return {"ref": f"{self.kind.value}/{self.name}.yaml"}

    @model_validator(mode="after")
    def resolve_spec_refs(self) -> Self:
        """Resolve all SpecRef fields in the spec to their referenced manifests."""
        for field in self.spec.model_fields_set:
            setattr(self.spec, field, self.__resolve_ref__(getattr(self.spec, field)))
        return self

    def __resolve_ref__(self, obj: Ref | dict | list) -> Spec:
        """Resolve a SpecRef, dict, or list to its corresponding Spec object(s)."""
        if isinstance(obj, Ref):
            return obj.resolve_ref(self._registry)
        if isinstance(obj, dict):
            return {k: self.__resolve_ref__(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.__resolve_ref__(v) for v in obj]
        return obj

    @model_serializer(mode="wrap")
    def serialize_ref(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        """Serialize the specification, including SpecRef's for fields with the type hint.

        Args:
            handler (SerializerFunctionWrapHandler): The handler used for serialization.

        Returns:
            dict[str, object]: The serialized specification or a reference dictionary.
        """
        serialized: dict = handler(self)
        type_hints = get_type_hints(self.spec)
        for field in serialized["spec"]:
            if self.__should_return_ref__(type_hints, field):
                serialized["spec"][field] = [manifest.ref for manifest in getattr(self.spec, field)]
        return serialized

    def __should_return_ref__(self, type_hints: dict, field: str) -> bool:
        """Determine if the field should be serialized as a reference based on its type hints."""
        if hasattr(type_hints[field], "__args__"):
            for _type in type_hints[field].__args__:
                if isinstance(_type, UnionType) and Ref in list(_type.__args__):
                    return True
        return False
