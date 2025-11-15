from typing import Annotated

from pydantic import BaseModel, Field

from orbitlab.data_types import ManifestKind
from orbitlab.manifest.schemas.base import BaseManifest, Metadata, Spec
from orbitlab.manifest.schemas.serialization import SerializeEnum


class SettingsMetadata(Metadata):
    cluster_mode: bool = False
    primary_node: Annotated[str | None, Field(default=None)]


class DefaultStorageSelections(BaseModel):
    vztmpl: Annotated[str | None, Field(default=None)]
    snippets: Annotated[str | None, Field(default=None)]
    imports: Annotated[str | None, Field(default=None)]
    iso: Annotated[str | None, Field(default=None)]
    backups: Annotated[str | None, Field(default=None)]
    rootdir: Annotated[str | None, Field(default=None)]


class SettingsSpec(Spec):
    default_storage_selections: DefaultStorageSelections = DefaultStorageSelections()
    default_ha_group: Annotated[str | None, Field(default=None)]


class OrbitLabSettingsManifest(BaseManifest[SettingsMetadata, SettingsSpec]):
    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.SETTINGS
