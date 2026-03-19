"""OrbitLab PKI pages."""
from typing import Final, Literal

import reflex as rx

from orbitlab.manifest.pki import IntermediateCertificateManifest, LeafCertificateManifest, RootCertificateManifest
from orbitlab.web import components
from orbitlab.web.layout import orbitlab_page
from orbitlab.web.utilities import EventGroup

from .dialogs import (
    CreateIntermediateCADialog,
    CreateLeafCertificateDialog,
    CreateRootCertificateDialog,
    DeleteIntermediateCertificateDialog,
    DeleteLeafCertificateDialog,
    DeleteRootCertificateDialog,
    ManageIntermediateCertDialog,
    ManageLeafCertDialog,
    ManageRootCertificateDialog,
)
from .states import (
    IntermediateCertificatesState,
    LeafCertificatesState,
    RootCertificatesState,
)

type CertFilter = Literal["All", "Valid", "Warning", "Expired"]


class CertificateAuthority:
    """A component for displaying root certificate authority information."""

    def __new__(cls, manifest: RootCertificateManifest) -> rx.Component:
        """Create and return the GridList item component."""
        return components.GridList.Item(
            rx.el.div(
                rx.el.div(
                    rx.icon("shield-check", size=24, class_name="text-sky-500"),
                    rx.match(
                        manifest.status,
                        ("warning", components.Badge("Expiring", color_scheme="orange")),
                        ("expired", components.Badge("Expired", color_scheme="red")),
                        components.Badge("Valid", color_scheme="green"),
                    ),
                    class_name="flex justify-between items-start",
                ),
                rx.el.div(
                    rx.el.h3(
                        manifest.spec.subject.common_name,
                        class_name="text-lg font-semibold text-gray-800 dark:text-gray-100",
                    ),
                    rx.el.p(
                        f"Issued by {manifest.spec.issued.issuer}",
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
                            rx.moment(manifest.spec.issued.not_before, format="YYYY-MM-DD"),
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
                                manifest.status == "expired",
                                rx.moment(manifest.spec.issued.not_after, to_now=True),
                                rx.moment(manifest.spec.issued.not_after, from_now=True),
                            ),
                            class_name="text-sm font-medium text-gray-800 dark:text-gray-200",
                        ),
                        class_name="flex-1 text-right",
                    ),
                    class_name="flex justify-between mt-6 pt-4 border-t border-gray-200 dark:border-gray-700",
                ),
            ),
            on_click=ManageRootCertificateDialog.manage(manifest.name),
            class_name="cursor-pointer",
        )


class IntermediateCertificate:
    """A component for displaying intermediate certificate authority information."""

    def __new__(cls, manifest: IntermediateCertificateManifest) -> rx.Component:
        """Create and return the GridList item component."""
        return components.GridList.Item(
            rx.el.div(
                rx.el.div(
                    rx.icon("shield-check", size=24, class_name="text-sky-500"),
                    rx.match(
                        manifest.status,
                        ("warning", components.Badge("Expiring", color_scheme="orange")),
                        ("expired", components.Badge("Expired", color_scheme="red")),
                        components.Badge("Valid", color_scheme="green"),
                    ),
                    class_name="flex justify-between items-start",
                ),
                rx.el.div(
                    rx.el.h3(
                        manifest.spec.subject.common_name,
                        class_name="text-lg font-semibold text-gray-800 dark:text-gray-100",
                    ),
                    rx.el.p(
                        f"Issued by {manifest.spec.issued.issuer}",
                        class_name="text-sm text-gray-500 dark:text-gray-400",
                    ),
                    class_name="mt-4",
                ),
                class_name="flex-grow",
            ),
            rx.el.div(
                rx.el.p(
                    f"*.{manifest.metadata.domain_constraint}",
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
                            rx.moment(manifest.spec.issued.not_before, format="YYYY-MM-DD"),
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
                                manifest.status == "expired",
                                rx.moment(manifest.spec.issued.not_after, to_now=True),
                                rx.moment(manifest.spec.issued.not_after, from_now=True),
                            ),
                            class_name="text-sm font-medium text-gray-800 dark:text-gray-200",
                        ),
                        class_name="flex-1 text-right",
                    ),
                    class_name="flex justify-between mt-2 pt-4 border-t border-gray-200 dark:border-gray-700",
                ),
            ),
            on_click=ManageIntermediateCertDialog.manage(manifest.name),
            class_name="cursor-pointer",
        )


class LeafCertificate:
    """A component for displaying leaf certificate information."""

    def __new__(cls, manifest: LeafCertificateManifest) -> rx.Component:
        """Create and return the GridList item component."""
        dns_sans = rx.Var.create(manifest.metadata.san_dns).to(list[str])
        ip_sans = rx.Var.create(manifest.metadata.san_ips).to(list[str])
        return components.GridList.Item(
            rx.el.div(
                rx.el.div(
                    rx.icon("shield-check", size=24, class_name="text-sky-500"),
                    rx.match(
                        manifest.status,
                        ("warning", components.Badge("Expiring", color_scheme="orange")),
                        ("expired", components.Badge("Expired", color_scheme="red")),
                        components.Badge("Valid", color_scheme="green"),
                    ),
                    class_name="flex justify-between items-start",
                ),
                rx.el.div(
                    rx.el.h3(
                        manifest.spec.subject.common_name,
                        class_name="text-lg font-semibold text-gray-800 dark:text-gray-100",
                    ),
                    rx.el.p(
                        f"Issued by {manifest.spec.issued.issuer}",
                        class_name="text-sm text-gray-500 dark:text-gray-400",
                    ),
                    class_name="mt-4",
                ),
                class_name="flex-grow",
            ),
            rx.el.div(
                rx.el.p(
                    rx.cond(
                        dns_sans.is_not_none(),
                        rx.foreach(dns_sans, lambda san: rx.text(san)),
                        rx.fragment(),
                    ),
                    rx.cond(
                        ip_sans.is_not_none(),
                        rx.foreach(ip_sans, lambda san: rx.text(san)),
                        rx.fragment(),
                    ),
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
                            rx.moment(manifest.spec.issued.not_before, format="YYYY-MM-DD"),
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
                                manifest.status == "expired",
                                rx.moment(manifest.spec.issued.not_after, to_now=True),
                                rx.moment(manifest.spec.issued.not_after, from_now=True),
                            ),
                            class_name="text-sm font-medium text-gray-800 dark:text-gray-200",
                        ),
                        class_name="flex-1 text-right",
                    ),
                    class_name="flex justify-between mt-2 pt-4 border-t border-gray-200 dark:border-gray-700",
                ),
            ),
            on_click=ManageLeafCertDialog.manage(manifest.name),
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
    async def set_ca_filter(state: RootCertificatesState, cert_filter: CertFilter) -> None:
        """Set the certificate filter for certificate authorities."""
        state.cert_filter = cert_filter

    @staticmethod
    @rx.event
    async def set_ica_filter(state: IntermediateCertificatesState, cert_filter: CertFilter) -> None:
        """Set the certificate filter for intermediate certificate authorities."""
        state.cert_filter = cert_filter

    @staticmethod
    @rx.event
    async def set_leaf_filter(state: LeafCertificatesState, cert_filter: CertFilter) -> None:
        """Set the certificate filter for leaf certificates."""
        state.cert_filter = cert_filter

    def __new__(cls, state: type[rx.State], label: CertFilter) -> rx.Component:
        """Create and return the button component."""
        if state == RootCertificatesState:
            return rx.el.button(
                label,
                on_click=cls.set_ca_filter(label),
                data_active=RootCertificatesState.cert_filter == label,
                class_name=cls.class_name,
            )
        if state == IntermediateCertificatesState:
            return rx.el.button(
                label,
                on_click=cls.set_ica_filter(label),
                data_active=IntermediateCertificatesState.cert_filter == label,
                class_name=cls.class_name,
            )
        if state == LeafCertificatesState:
            return rx.el.button(
                label,
                on_click=cls.set_leaf_filter(label),
                data_active=LeafCertificatesState.cert_filter == label,
                class_name=cls.class_name,
            )
        msg = f"Unexpected state class: {state}"
        raise ValueError(msg)


@rx.page("/secrets-pki/pki/certificate-authorities")
@orbitlab_page
def certificate_authorities_page() -> rx.Component:
    """Render the certificate authorities management page."""
    return rx.el.div(
        components.PageHeader(
            "Certificate Authority Management",
            components.Buttons.Secondary(
                "Refresh",
                icon="refresh-ccw",
                on_click=RootCertificatesState.cache_clear("all"),
            ),
            components.Buttons.Primary(
                "Create CA",
                icon="plus",
                on_click=components.Dialog.open(CreateRootCertificateDialog.dialog_id),
            ),
        ),
        CreateRootCertificateDialog(),
        ManageRootCertificateDialog(),
        DeleteRootCertificateDialog(),
        rx.el.div(
            FilterButton(RootCertificatesState, "All"),
            FilterButton(RootCertificatesState, "Valid"),
            FilterButton(RootCertificatesState, "Warning"),
            FilterButton(RootCertificatesState, "Expired"),
            class_name="flex items-center gap-2 mb-8",
        ),
        components.GridList(
            rx.foreach(RootCertificatesState.filtered, lambda ca: CertificateAuthority(ca)),
        ),
        class_name="w-full h-full",
    )


@rx.page("/secrets-pki/pki/intermediate-certificates")
@orbitlab_page
def intermediate_certificates_page() -> rx.Component:
    """Render the intermediate certificates management page."""
    return rx.el.div(
        components.PageHeader(
            "Intermediate Signing Certificates",
            components.Buttons.Secondary(
                "Refresh",
                icon="refresh-ccw",
                on_click=IntermediateCertificatesState.cache_clear("all"),
            ),
            components.Buttons.Primary(
                "Create Signing CA",
                icon="plus",
                on_click=components.Dialog.open(CreateIntermediateCADialog.dialog_id),
            ),
        ),
        CreateIntermediateCADialog(),
        ManageIntermediateCertDialog(),
        DeleteIntermediateCertificateDialog(),
        rx.el.div(
            FilterButton(IntermediateCertificatesState, "All"),
            FilterButton(IntermediateCertificatesState, "Valid"),
            FilterButton(IntermediateCertificatesState, "Warning"),
            FilterButton(IntermediateCertificatesState, "Expired"),
            class_name="flex items-center gap-2 mb-8",
        ),
        components.GridList(
            rx.foreach(IntermediateCertificatesState.filtered, lambda ca: IntermediateCertificate(ca)),
        ),
        class_name="w-full h-full",
    )


@rx.page("/secrets-pki/pki/leaf-certificates")
@orbitlab_page
def leaf_certificates_page() -> rx.Component:
    """Render the leaf certificates management page."""
    return rx.el.div(
        components.PageHeader(
            "Leaf Certificates",
            components.Buttons.Secondary(
                "Refresh",
                icon="refresh-ccw",
                on_click=LeafCertificatesState.cache_clear("all"),
            ),
            components.Buttons.Primary(
                "Create Leaf Certificate",
                icon="plus",
                on_click=components.Dialog.open(CreateLeafCertificateDialog.dialog_id),
            ),
        ),
        CreateLeafCertificateDialog(),
        ManageLeafCertDialog(),
        DeleteLeafCertificateDialog(),
        rx.el.div(
            FilterButton(LeafCertificatesState, "All"),
            FilterButton(LeafCertificatesState, "Valid"),
            FilterButton(LeafCertificatesState, "Warning"),
            FilterButton(LeafCertificatesState, "Expired"),
            class_name="flex items-center gap-2 mb-8",
        ),
        components.GridList(
            rx.foreach(LeafCertificatesState.filtered, lambda ca: LeafCertificate(ca)),
        ),
        class_name="w-full h-full",
    )
