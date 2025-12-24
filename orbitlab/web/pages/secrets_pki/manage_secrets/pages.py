"""OrbitLab Secrets Management."""

import reflex as rx

from orbitlab.services.vault.client import SecretVault
from orbitlab.web import components
from orbitlab.web.pages.secrets_pki.layout import secrets_pki_page

from .tables import SecretsTable


@rx.event
async def test_thing(state: rx.State):
    print(SecretVault().get(secret_name="/orbitlab/sector/gateway/1000", version=1).secret_string.get_secret_value())


@rx.page("/secrets-pki/secrets")
@secrets_pki_page
def manage_secrets_page() -> rx.Component:
    """Render the secrets management page."""
    return rx.el.div(
        components.PageHeader(
            "Secrets Management",
            components.Buttons.Primary(
                "TEST",
                on_click=test_thing,
            ),
        ),
        SecretsTable(),
    )
