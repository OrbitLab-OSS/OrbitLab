"""OrbitLab Secrets Management States."""

import reflex as rx

from orbitlab.redis.models import Secret


class CreateSecretDialogState(rx.State):
    """State management for the create secret dialog."""

    view_secret_value: rx.Field[bool] = rx.field(default=False)


class DeleteSecretDialogState(rx.State):
    """State management for the delete secret dialog."""

    secret: rx.Field[str] = rx.field(default="")
    delete_disabled: rx.Field[bool] = rx.field(default=True)
