"""OrbitLab Secrets Management."""

import reflex as rx

from orbitlab.web import components
from orbitlab.web.layout import orbitlab_page

from .dialogs import CreateSecretDialog
from .tables import SecretsTable


@rx.page("/secrets-pki/secrets")
@orbitlab_page
def manage_secrets_page() -> rx.Component:
    """Render the secrets management page."""
    return rx.el.div(
        components.PageHeader(
            "Secrets Management",
            components.Buttons.Primary(
                "Create Secret",
                icon="plus",
                on_click=components.Dialog.open(CreateSecretDialog.dialog_id),
            ),
        ),
        SecretsTable(),
        CreateSecretDialog(),
    )
