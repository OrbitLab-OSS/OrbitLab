"""OrbitLab PKI pages."""
from typing import Final, Literal

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.manifest.secrets import CertificateManifest
from orbitlab.web.components import Badge, Buttons, Dialog, GridList, PageHeader
from orbitlab.web.pages.secrets_pki.layout import secrets_pki_page
from orbitlab.web.states.utilities import EventGroup

from .dialogs import (
    ConfirmRevokeCADialog,
    ConfirmRevokeIntermediateCADialog,
    CreateCertificateAuthorityDialog,
    CreateIntermediateCADialog,
    ManageCertificateAuthorityDialog,
    ManageIntermediateCertDialog,
)
from .states import CAState, IntermediateCAState, ManageCA, ManageIntermediateCerts

type CertFilter = Literal["All", "Valid", "Warning", "Expired"]


class CertificateAuthority(EventGroup):
    """A component for displaying root certificate authority information.

    This class creates a grid list item component that displays root CA
    details including status, name, issuer, and expiration dates.
    It also handles click events to open the management dialog for the root CA.
    """

    @staticmethod
    @rx.event
    async def manage_root_ca(state: ManageCA, ca: dict | CertificateManifest) -> FrontendEvents:
        """Open the management dialog for a root certificate authority."""
        state.manifest = CertificateManifest.model_validate(ca) if isinstance(ca, dict) else ca
        return Dialog.open(ManageCertificateAuthorityDialog.dialog_id)

    def __new__(cls, ca: CertificateManifest) -> rx.Component:
        """Create and return the GridList item component."""
        return GridList.Item(
            rx.el.div(
                rx.el.div(
                    rx.icon("shield-check", size=24, class_name="text-sky-500"),
                    rx.match(
                        ca.metadata.status,
                        ("warning", Badge("Expiring", color_scheme="orange")),
                        ("expired", Badge("Expired", color_scheme="red")),
                        Badge("Valid", color_scheme="green"),
                    ),
                    class_name="flex justify-between items-start",
                ),
                rx.el.div(
                    rx.el.h3(
                        ca.name,
                        class_name="text-lg font-semibold text-gray-800 dark:text-gray-100",
                    ),
                    rx.el.p(
                        f"Issued by {ca.metadata.issuer}",
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
                            rx.moment(ca.metadata.not_before, format="YYYY-MM-DD"),
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
                                ca.metadata.status == "expired",
                                rx.moment(ca.metadata.not_after, to_now=True),
                                rx.moment(ca.metadata.not_after, from_now=True),
                            ),
                            class_name="text-sm font-medium text-gray-800 dark:text-gray-200",
                        ),
                        class_name="flex-1 text-right",
                    ),
                    class_name="flex justify-between mt-6 pt-4 border-t border-gray-200 dark:border-gray-700",
                ),
            ),
            on_click=cls.manage_root_ca(ca),
            class_name="cursor-pointer",
        )


class IntermediateCertificate(EventGroup):
    """A component for displaying intermediate certificate authority information.

    This class creates a grid list item component that displays intermediate CA
    details including status, name, issuer, domain constraints, and expiration dates.
    It also handles click events to open the management dialog for the intermediate CA.
    """

    @staticmethod
    @rx.event
    async def manage_intermediate_ca(state: ManageIntermediateCerts, ca: dict | CertificateManifest) -> FrontendEvents:
        """Open the management dialog for an intermediate certificate authority."""
        state.manifest = CertificateManifest.model_validate(ca) if isinstance(ca, dict) else ca
        return Dialog.open(ManageIntermediateCertDialog.dialog_id)

    def __new__(cls, ca: CertificateManifest) -> rx.Component:
        """Create and return the GridList item component."""
        return GridList.Item(
            rx.el.div(
                rx.el.div(
                    rx.icon("shield-check", size=24, class_name="text-sky-500"),
                    rx.match(
                        ca.metadata.status,
                        ("warning", Badge("Expiring", color_scheme="orange")),
                        ("expired", Badge("Expired", color_scheme="red")),
                        Badge("Valid", color_scheme="green"),
                    ),
                    class_name="flex justify-between items-start",
                ),
                rx.el.div(
                    rx.el.h3(
                        ca.name,
                        class_name="text-lg font-semibold text-gray-800 dark:text-gray-100",
                    ),
                    rx.el.p(
                        f"Issued by {ca.metadata.issuer}",
                        class_name="text-sm text-gray-500 dark:text-gray-400",
                    ),
                    class_name="mt-4",
                ),
                class_name="flex-grow",
            ),
            rx.el.div(
                rx.el.p(
                    f"*.{ca.metadata.domain_constraint}",
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
                            rx.moment(ca.metadata.not_before, format="YYYY-MM-DD"),
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
                                ca.metadata.status == "expired",
                                rx.moment(ca.metadata.not_after, to_now=True),
                                rx.moment(ca.metadata.not_after, from_now=True),
                            ),
                            class_name="text-sm font-medium text-gray-800 dark:text-gray-200",
                        ),
                        class_name="flex-1 text-right",
                    ),
                    class_name="flex justify-between mt-2 pt-4 border-t border-gray-200 dark:border-gray-700",
                ),
            ),
            on_click=cls.manage_intermediate_ca(ca),
            class_name="cursor-pointer",
        )


class FilterButton(EventGroup):
    """A button component for filtering certificates by status.

    This class creates filter buttons that can be used to filter certificate
    authorities or intermediate certificates by their status (All, Valid, Warning, Expired).
    The buttons have different styling based on their active state.
    """
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
    async def set_ca_filter(state: CAState, cert_filter: CertFilter) -> None:
        """Set the certificate filter for certificate authorities."""
        state.cert_filter = cert_filter

    @staticmethod
    @rx.event
    async def set_ica_filter(state: IntermediateCAState, cert_filter: CertFilter) -> None:
        """Set the certificate filter for intermediate certificate authorities."""
        state.cert_filter = cert_filter

    def __new__(cls, state: type[rx.State], label: CertFilter) -> rx.Component:
        """Create and return the button component."""
        if state == CAState:
            return rx.el.button(
                label,
                on_click=cls.set_ca_filter(label),
                data_active=CAState.cert_filter == label,
                class_name=cls.class_name,
            )
        if state == IntermediateCAState:
            return rx.el.button(
                label,
                on_click=cls.set_ica_filter(label),
                data_active=IntermediateCAState.cert_filter == label,
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
            FilterButton(CAState, "All"),
            FilterButton(CAState, "Valid"),
            FilterButton(CAState, "Warning"),
            FilterButton(CAState, "Expired"),
            class_name="flex items-center gap-2 mb-8",
        ),
        GridList(
            rx.foreach(CAState.filtered_certificates, lambda ca: CertificateAuthority(ca)),
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
            FilterButton(IntermediateCAState, "All"),
            FilterButton(IntermediateCAState, "Valid"),
            FilterButton(IntermediateCAState, "Warning"),
            FilterButton(IntermediateCAState, "Expired"),
            class_name="flex items-center gap-2 mb-8",
        ),
        GridList(
            rx.foreach(IntermediateCAState.filtered_certificates, lambda ca: IntermediateCertificate(ca)),
        ),
        class_name="w-full h-full",
    )
