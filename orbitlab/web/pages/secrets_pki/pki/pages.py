"""OrbitLab PKI pages."""
from typing import Final, Literal

import reflex as rx

from orbitlab.manifest.secrets import CertificateManifest
from orbitlab.web.components import Badge, Buttons, Dialog, GridList, PageHeader
from orbitlab.web.pages.secrets_pki.layout import secrets_pki_page
from orbitlab.web.utilities import EventGroup

from .dialogs import (
    ConfirmRevokeCADialog,
    ConfirmRevokeIntermediateCADialog,
    CreateCertificateAuthorityDialog,
    CreateIntermediateCADialog,
    ManageCertificateAuthorityDialog,
    ManageIntermediateCertDialog,
)
from .states import (
    CertificateAuthoritiesState,
    IntermediateCertificatesState,
    ManageCertificateState,
)

type CertFilter = Literal["All", "Valid", "Warning", "Expired"]


class CertificateAuthority:
    """A component for displaying root certificate authority information."""

    def __new__(cls, certificate_authority: CertificateManifest) -> rx.Component:
        """Create and return the GridList item component."""
        return GridList.Item(
            rx.el.div(
                rx.el.div(
                    rx.icon("shield-check", size=24, class_name="text-sky-500"),
                    rx.match(
                        certificate_authority.metadata.status,
                        ("warning", Badge("Expiring", color_scheme="orange")),
                        ("expired", Badge("Expired", color_scheme="red")),
                        Badge("Valid", color_scheme="green"),
                    ),
                    class_name="flex justify-between items-start",
                ),
                rx.el.div(
                    rx.el.h3(
                        certificate_authority.name,
                        class_name="text-lg font-semibold text-gray-800 dark:text-gray-100",
                    ),
                    rx.el.p(
                        f"Issued by {certificate_authority.metadata.issuer}",
                        class_name="text-sm text-gray-500 dark:text-gray-400",
                    ),
                    class_name="mt-4",
                ),
                class_name="flex-grow",
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.div(
                        rx.el.p(
                            "Issued On",
                            class_name="text-xs text-gray-500 dark:text-gray-400",
                        ),
                        rx.el.p(
                            rx.moment(certificate_authority.metadata.not_before, format="YYYY-MM-DD"),
                            class_name="text-sm font-medium text-gray-800 dark:text-gray-200",
                        ),
                        class_name="flex-1 text-left",
                    ),
                    rx.el.div(
                        rx.el.p(
                            "Expires",
                            class_name="text-xs text-gray-500 dark:text-gray-400",
                        ),
                        rx.el.p(
                            rx.cond(
                                certificate_authority.metadata.status == "expired",
                                rx.moment(certificate_authority.metadata.not_after, to_now=True),
                                rx.moment(certificate_authority.metadata.not_after, from_now=True),
                            ),
                            class_name="text-sm font-medium text-gray-800 dark:text-gray-200",
                        ),
                        class_name="flex-1 text-right",
                    ),
                    class_name="flex justify-between mt-6 pt-4 border-t border-gray-200 dark:border-gray-700",
                ),
            ),
            on_click=[
                ManageCertificateState.load(certificate_authority.name),
                Dialog.open(ManageCertificateAuthorityDialog.dialog_id),
            ],
            class_name="cursor-pointer",
        )


class IntermediateCertificate:
    """A component for displaying intermediate certificate authority information."""

    def __new__(cls, intermediate_certificate: CertificateManifest) -> rx.Component:
        """Create and return the GridList item component."""
        return GridList.Item(
            rx.el.div(
                rx.el.div(
                    rx.icon("shield-check", size=24, class_name="text-sky-500"),
                    rx.match(
                        intermediate_certificate.metadata.status,
                        ("warning", Badge("Expiring", color_scheme="orange")),
                        ("expired", Badge("Expired", color_scheme="red")),
                        Badge("Valid", color_scheme="green"),
                    ),
                    class_name="flex justify-between items-start",
                ),
                rx.el.div(
                    rx.el.h3(
                        intermediate_certificate.name,
                        class_name="text-lg font-semibold text-gray-800 dark:text-gray-100",
                    ),
                    rx.el.p(
                        f"Issued by {intermediate_certificate.metadata.issuer}",
                        class_name="text-sm text-gray-500 dark:text-gray-400",
                    ),
                    class_name="mt-4",
                ),
                class_name="flex-grow",
            ),
            rx.el.div(
                rx.el.p(
                    f"*.{intermediate_certificate.metadata.domain_constraint}",
                    class_name=(
                        "text-sm text-gray-500 dark:text-gray-400 mt-4 pt-2 border-t border-gray-200 "
                        "dark:border-gray-700"
                    ),
                ),
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.div(
                        rx.el.p(
                            "Issued On",
                            class_name="text-xs text-gray-500 dark:text-gray-400",
                        ),
                        rx.el.p(
                            rx.moment(intermediate_certificate.metadata.not_before, format="YYYY-MM-DD"),
                            class_name="text-sm font-medium text-gray-800 dark:text-gray-200",
                        ),
                        class_name="flex-1 text-left",
                    ),
                    rx.el.div(
                        rx.el.p(
                            "Expires",
                            class_name="text-xs text-gray-500 dark:text-gray-400",
                        ),
                        rx.el.p(
                            rx.cond(
                                intermediate_certificate.metadata.status == "expired",
                                rx.moment(intermediate_certificate.metadata.not_after, to_now=True),
                                rx.moment(intermediate_certificate.metadata.not_after, from_now=True),
                            ),
                            class_name="text-sm font-medium text-gray-800 dark:text-gray-200",
                        ),
                        class_name="flex-1 text-right",
                    ),
                    class_name="flex justify-between mt-2 pt-4 border-t border-gray-200 dark:border-gray-700",
                ),
            ),
            on_click=[
                ManageCertificateState.load(intermediate_certificate.name),
                Dialog.open(ManageIntermediateCertDialog.dialog_id),
            ],
            class_name="cursor-pointer",
        )


class FilterButton(EventGroup):
    """A button component for filtering certificates by status."""

    class_name: Final = (
        "flex items-start px-3 py-2.5 rounded-xl data-[active=true]:bg-sky-100 "
        "data-[active=true]:text-sky-600 data-[active=true]:dark:bg-sky-900/50 "
        "data-[active=true]:dark:text-sky-300 data-[active=false]:text-gray-500 "
        "data-[active=false]:dark:text-gray-400 "
        "data-[active=false]:hover:bg-gray-100 data-[active=false]:dark:hover:bg-gray-800 "
        "data-[active=false]:hover:text-gray-800 data-[active=false]:dark:hover:text-gray-200"
    )

    @staticmethod
    @rx.event
    async def set_ca_filter(state: CertificateAuthoritiesState, cert_filter: CertFilter) -> None:
        """Set the certificate filter for certificate authorities."""
        state.cert_filter = cert_filter

    @staticmethod
    @rx.event
    async def set_ica_filter(state: IntermediateCertificatesState, cert_filter: CertFilter) -> None:
        """Set the certificate filter for intermediate certificate authorities."""
        state.cert_filter = cert_filter

    def __new__(cls, state: type[rx.State], label: CertFilter) -> rx.Component:
        """Create and return the button component."""
        if state == CertificateAuthoritiesState:
            return rx.el.button(
                label,
                on_click=cls.set_ca_filter(label),
                data_active=CertificateAuthoritiesState.cert_filter == label,
                class_name=cls.class_name,
            )
        if state == IntermediateCertificatesState:
            return rx.el.button(
                label,
                on_click=cls.set_ica_filter(label),
                data_active=IntermediateCertificatesState.cert_filter == label,
                class_name=cls.class_name,
            )
        msg = f"Unexpected state class: {state}"
        raise ValueError(msg)


@rx.page("/secrets-pki/pki/certificate-authorities")
@secrets_pki_page
def certificate_authorities_page() -> rx.Component:
    """Render the certificate authorities management page."""
    return rx.el.div(
        PageHeader(
            "Certificate Authority Management",
            Buttons.Primary(
                "Create CA",
                icon="plus",
                on_click=Dialog.open(CreateCertificateAuthorityDialog.dialog_id),
            ),
        ),
        CreateCertificateAuthorityDialog(),
        ManageCertificateAuthorityDialog(),
        ConfirmRevokeCADialog(),
        rx.el.div(
            FilterButton(CertificateAuthoritiesState, "All"),
            FilterButton(CertificateAuthoritiesState, "Valid"),
            FilterButton(CertificateAuthoritiesState, "Warning"),
            FilterButton(CertificateAuthoritiesState, "Expired"),
            class_name="flex items-center gap-2 mb-8",
        ),
        GridList(
            rx.foreach(CertificateAuthoritiesState.filtered_certificates, lambda ca: CertificateAuthority(ca)),
        ),
        class_name="w-full h-full",
    )


@rx.page("/secrets-pki/pki/intermediate-certificates")
@secrets_pki_page
def intermediate_certificates_page() -> rx.Component:
    """Render the intermediate certificates management page."""
    return rx.el.div(
        PageHeader(
            "Intermediate Signing Certificates",
            Buttons.Primary(
                "Create Signing CA",
                icon="plus",
                on_click=Dialog.open(CreateIntermediateCADialog.dialog_id),
            ),
        ),
        CreateIntermediateCADialog(),
        ManageIntermediateCertDialog(),
        ConfirmRevokeIntermediateCADialog(),
        rx.el.div(
            FilterButton(IntermediateCertificatesState, "All"),
            FilterButton(IntermediateCertificatesState, "Valid"),
            FilterButton(IntermediateCertificatesState, "Warning"),
            FilterButton(IntermediateCertificatesState, "Expired"),
            class_name="flex items-center gap-2 mb-8",
        ),
        GridList(
            rx.foreach(IntermediateCertificatesState.filtered_certificates, lambda ca: IntermediateCertificate(ca)),
        ),
        class_name="w-full h-full",
    )
