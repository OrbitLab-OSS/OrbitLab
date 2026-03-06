"""OrbitLab Secrets & PKI Dashboard."""

import reflex as rx

from orbitlab.web.components.page_header import PageHeader

from orbitlab.web.layout import orbitlab_page


@rx.page("/secrets-pki")
@orbitlab_page
def secrets_pki_dashboard() -> rx.Component:
    """Render the secrets and PKI management dashboard page."""
    return rx.el.div(
        PageHeader(
            "Secrets and PKI Management",
        ),
    )
