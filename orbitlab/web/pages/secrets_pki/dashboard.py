import reflex as rx

from orbitlab.web.components import PageHeader, SideBar
from orbitlab.web.pages.layout import DefaultLayout

from .certificate_authorities import CertificateAuthorities
from .intermediate_certificates import IntermediateCertificateAuthorities


class Dashboard:
    def __new__(cls):
        return rx.el.div(
            PageHeader(
                "Secrets and PKI Management",
            ),
        )


class ManageSecrets:
    def __new__(cls):
        return rx.flex()


@rx.page("/secrets-pki")
def secrets_and_pki_pages() -> rx.Component:
    """Proxmox Nodes Page."""
    side_bar, sidebar_id = SideBar(
        SideBar.NavItem(icon="layout-dashboard", text="Dashboard"),
        SideBar.SectionHeader(title="Secrets"),
        SideBar.NavItem(icon="book-key", text="Manage Secrets"),
        SideBar.SectionHeader(title="PKI"),
        SideBar.NavItem(icon="gavel", text="Certificate Authorities"),
        SideBar.NavItem(icon="shield-plus", text="Intermediate CAs"),
        default_page="Dashboard",
        title="Secrets & PKI",
    )
    return DefaultLayout(
        side_bar,
        rx.match(
            SideBar.Manager.registered[sidebar_id].active_page,
            ("Dashboard", Dashboard()),
            ("Manage Secrets", ManageSecrets()),
            ("Certificate Authorities", CertificateAuthorities()),
            ("Intermediate CAs", IntermediateCertificateAuthorities()),
            Dashboard(),
        ),
    )
