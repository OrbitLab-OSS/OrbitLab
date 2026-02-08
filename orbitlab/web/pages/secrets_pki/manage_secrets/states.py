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


class DeleteSecretDialogState(rx.State):
    """State management for the delete secret dialog."""

    secret: rx.Field[SecretManifest | None] = rx.field(default=None)
    delete_disabled: rx.Field[bool] = rx.field(default=True)

    @rx.var
    def secret_id(self) -> str:
        """Return the name of the selected secret, or an empty string if none is selected."""
        if self.secret:
            return self.secret.spec.secret_name
        return ""
