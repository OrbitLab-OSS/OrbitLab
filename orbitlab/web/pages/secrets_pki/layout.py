"""OrbitLab Secrets & PKI Layout."""

from collections.abc import Callable

import reflex as rx

from orbitlab.web.components.sidebar import SideBar
from orbitlab.web.pages.layout import DefaultLayout
from orbitlab.web.splash_page import require_configuration


def secrets_pki_page(page: Callable[[], rx.Component]) -> Callable[[], rx.Component]:
    """Create a secrets and PKI page layout with sidebar navigation."""

    @require_configuration
    def wrapped() -> rx.Component:
        return DefaultLayout(
            SideBar(
                SideBar.NavItem(icon="layout-dashboard", text="Dashboard", href="/secrets-pki"),
                SideBar.SectionHeader(title="Secrets"),
                SideBar.NavItem(icon="book-key", text="Manage Secrets", href="/secrets-pki/secrets"),
                SideBar.SectionHeader(title="PKI"),
                SideBar.NavItem(
                    icon="gavel",
                    text="Certificate Authorities",
                    href="/secrets-pki/pki/certificate-authorities",
                ),
                SideBar.NavItem(
                    icon="shield-plus",
                    text="Intermediate CAs",
                    href="/secrets-pki/pki/intermediate-certificates",
                ),
                title="Secrets & PKI",
            ),
            page(),
        )

    return wrapped
