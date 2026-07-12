"""OrbitLab Secrets Management."""

import reflex as rx

from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.layout import orbitlab_page

from .dialogs import CreateSecretDialog, DeleteSecretDialog
from .tables import SecretsTable


@rx.page("/secrets-pki/secrets")
@orbitlab_page
def manage_secrets_page() -> rx.Component:
    """Render the secrets management page."""
    return rx.el.div(
        tailwind.PageHeader(
            "Secrets Management",
            tailwind.Buttons.Primary(
                "Create Secret",
                icon="plus",
                on_click=tailwind.Dialog.open(CreateSecretDialog.dialog_id),
            ),
        ),
        SecretsTable(
            name="Secrets",
            headers=["ID", "Version", "Description", "Value", ""],
            data=OrbitLabState.secrets,
            refresh=OrbitLabState.cache_clear("secrets")
        ),
        CreateSecretDialog(),
        DeleteSecretDialog(),
    )
