from typing import Annotated

from orbitlab.data_types import ManifestKind

from .base import BaseManifest, Metadata, Spec
from .serialization import SerializeEnum


class ClusterMetadata(Metadata):
    name: str
    version: int
    node_count: int


class ClusterSpec(Spec):
    quorate: bool


class ClusterManifest(BaseManifest[ClusterMetadata, ClusterSpec]):
    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.CLUSTER
