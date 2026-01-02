"""Schema definitions for Autoscaling Pool manifests in OrbitLab."""

from typing import Annotated

from pydantic import BaseModel

from orbitlab.data_types import HealthCheckProtocol, ManifestKind
from orbitlab.manifest.serialization import SerializeEnum

from .base import BaseManifest, Metadata, Spec


class AutoscalingLXCMetadata(Metadata):
    """Metadata for an autoscaling LXC pool, including the pool name."""

    pool_name: str


class HealthCheck(BaseModel):
    """Defines the health check configuration for an autoscaling LXC pool."""

    protocol: Annotated[HealthCheckProtocol, SerializeEnum]
    port: int
    path: str
    timeout_seconds: int
    success_count: int
    failure_count: int
    interval_seconds: int
    warmup_seconds: int


class AutoscalingLXCSpec(Spec):
    """Specification for an autoscaling LXC pool, including health check and OS template."""

    health_check: HealthCheck
    os_template: str
    # TODO: Finish


class AutoscalingLXCManifest(BaseManifest[AutoscalingLXCMetadata, AutoscalingLXCSpec]):
    """Manifest for an autoscaling LXC pool in OrbitLab."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.AUTOSCALING
