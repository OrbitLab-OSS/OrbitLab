"""OrbitLab Secrets Management States."""

import reflex as rx

from orbitlab.manifest.secrets import SecretManifest
from orbitlab.web.utilities import CacheBuster


class SecretsState(CacheBuster, rx.State):
    """State management for certificate manifests."""

    @rx.var(deps=["_cached_secrets"])
    def secrets(self) -> list[SecretManifest]:
        """Get all existing secret manifests."""
        return [SecretManifest.load(name=name) for name in SecretManifest.get_existing()]
