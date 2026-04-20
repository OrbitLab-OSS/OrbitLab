"""OrbitLab Secrets Management States."""

import reflex as rx

from orbitlab.redis.clients import SecretsClient
from orbitlab.redis.models import Secret
from orbitlab.web.utilities import CacheBuster


class SecretsState(CacheBuster, rx.State):
    """State management for certificate manifests."""

    @rx.var(deps=["_cached_secrets"])
    async def secrets(self) -> list[Secret]:
        """Get all existing secret manifests."""
        return await SecretsClient().list_secrets()


class CreateSecretDialogState(rx.State):
    """State management for the create secret dialog."""

    view_secret_value: rx.Field[bool] = rx.field(default=False)


class DeleteSecretDialogState(rx.State):
    """State management for the delete secret dialog."""

    secret: rx.Field[Secret | None] = rx.field(default=None)
    delete_disabled: rx.Field[bool] = rx.field(default=True)
