"""OrbitLab Secrets Management."""

import reflex as rx

from orbitlab.web.pages.secrets_pki.layout import secrets_pki_page


@rx.page("/secrets-pki/secrets")
@secrets_pki_page
def manage_secrets_page() -> rx.Component:
    """Render the secrets management page."""
    return rx.flex()
