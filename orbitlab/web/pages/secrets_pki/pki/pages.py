"""OrbitLab PKI pages."""
from typing import Final, Literal

import reflex as rx

from orbitlab.redis.models import IntermediateCert, LeafCert, RootCert
from orbitlab.web import tailwind
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

    def __new__(cls, root_cert: RootCert) -> rx.Component:
        """Create and return the GridList item component."""
        return tailwind.GridList.Item(
            rx.el.div(
                rx.el.div(
                    rx.icon("shield-check", size=24, class_name="text-sky-500"),
                    rx.match(
                        root_cert.status,
                        ("warning", tailwind.Badge("Expiring", color_scheme="orange")),
                        ("expired", tailwind.Badge("Expired", color_scheme="red")),
                        tailwind.Badge("Valid", color_scheme="green"),
                    ),
                    class_name="flex justify-between items-start",
                ),
                rx.el.div(
                    rx.el.h3(
                        root_cert.subject.common_name,
                        class_name="text-lg font-semibold text-gray-800 dark:text-gray-100",
                    ),
                    rx.el.p(
                        f"Issued by {root_cert.issuer}",
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
                            rx.moment(root_cert.not_before, format="YYYY-MM-DD"),
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
                                root_cert.status == "expired",
                                rx.moment(root_cert.not_after, to_now=True),
                                rx.moment(root_cert.not_after, from_now=True),
                            ),
                            class_name="text-sm font-medium text-gray-800 dark:text-gray-200",
                        ),
                        class_name="flex-1 text-right",
                    ),
                    class_name="flex justify-between mt-6 pt-4 border-t border-gray-200 dark:border-gray-700",
                ),
            ),
            on_click=ManageRootCertificateDialog.manage(root_cert.subject.common_name),
            class_name="cursor-pointer",
        )


class IntermediateCertificate:
    """A component for displaying intermediate certificate authority information."""

    def __new__(cls, intermediate_cert: IntermediateCert) -> rx.Component:
        """Create and return the GridList item component."""
        return tailwind.GridList.Item(
            rx.el.div(
                rx.el.div(
                    rx.icon("shield-check", size=24, class_name="text-sky-500"),
                    rx.match(
                        intermediate_cert.status,
                        ("warning", tailwind.Badge("Expiring", color_scheme="orange")),
                        ("expired", tailwind.Badge("Expired", color_scheme="red")),
                        tailwind.Badge("Valid", color_scheme="green"),
                    ),
                    class_name="flex justify-between items-start",
                ),
                rx.el.div(
                    rx.el.h3(
                        intermediate_cert.subject.common_name,
                        class_name="text-lg font-semibold text-gray-800 dark:text-gray-100",
                    ),
                    rx.el.p(
                        f"Issued by {intermediate_cert.issuer}",
                        class_name="text-sm text-gray-500 dark:text-gray-400",
                    ),
                    class_name="mt-4",
                ),
                class_name="flex-grow",
            ),
            rx.el.div(
                rx.el.p(
                    f"*.{intermediate_cert.domain_constraint}",
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
                            rx.moment(intermediate_cert.not_before, format="YYYY-MM-DD"),
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
                                intermediate_cert.status == "expired",
                                rx.moment(intermediate_cert.not_after, to_now=True),
                                rx.moment(intermediate_cert.not_after, from_now=True),
                            ),
                            class_name="text-sm font-medium text-gray-800 dark:text-gray-200",
                        ),
                        class_name="flex-1 text-right",
                    ),
                    class_name="flex justify-between mt-2 pt-4 border-t border-gray-200 dark:border-gray-700",
                ),
            ),
            on_click=ManageIntermediateCertDialog.manage(intermediate_cert.subject.common_name),
            class_name="cursor-pointer",
        )


class LeafCertificate:
    """A component for displaying leaf certificate information."""

    def __new__(cls, leaf_cert: LeafCert) -> rx.Component:
        """Create and return the GridList item component."""
        return tailwind.GridList.Item(
            rx.el.div(
                rx.el.div(
                    rx.icon("shield-check", size=24, class_name="text-sky-500"),
                    rx.match(
                        leaf_cert.status,
                        ("warning", tailwind.Badge("Expiring", color_scheme="orange")),
                        ("expired", tailwind.Badge("Expired", color_scheme="red")),
                        tailwind.Badge("Valid", color_scheme="green"),
                    ),
                    class_name="flex justify-between items-start",
                ),
                rx.el.div(
                    rx.el.h3(
                        leaf_cert.subject.common_name,
                        class_name="text-lg font-semibold text-gray-800 dark:text-gray-100",
                    ),
                    rx.el.p(
                        f"Issued by {leaf_cert.issuer}",
                        class_name="text-sm text-gray-500 dark:text-gray-400",
                    ),
                    class_name="mt-4",
                ),
                class_name="flex-grow",
            ),
            rx.el.div(
                rx.el.p(
                    rx.cond(
                        rx.Var.create(leaf_cert.san_dns).to(list[str]).length() > 0,
                        rx.foreach(leaf_cert.san_dns, lambda san: rx.text(san)),
                        rx.fragment(),
                    ),
                    rx.cond(
                        rx.Var.create(leaf_cert.san_ips).to(list[str]).length() > 0,
                        rx.foreach(leaf_cert.san_ips, lambda san: rx.text(san)),
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
                            rx.moment(leaf_cert.not_before, format="YYYY-MM-DD"),
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
                                leaf_cert.status == "expired",
                                rx.moment(leaf_cert.not_after, to_now=True),
                                rx.moment(leaf_cert.not_after, from_now=True),
                            ),
                            class_name="text-sm font-medium text-gray-800 dark:text-gray-200",
                        ),
                        class_name="flex-1 text-right",
                    ),
                    class_name="flex justify-between mt-2 pt-4 border-t border-gray-200 dark:border-gray-700",
                ),
            ),
            on_click=ManageLeafCertDialog.manage(leaf_cert.subject.common_name),
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
        tailwind.PageHeader(
            "Certificate Authority Management",
            tailwind.Buttons.Secondary(
                "Refresh",
                icon="refresh-ccw",
                on_click=RootCertificatesState.cache_clear("all"),
            ),
            tailwind.Buttons.Primary(
                "Create CA",
                icon="plus",
                on_click=tailwind.Dialog.open(CreateRootCertificateDialog.dialog_id),
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
        tailwind.GridList(
            rx.foreach(RootCertificatesState.filtered, lambda ca: CertificateAuthority(ca)),
        ),
        class_name="w-full h-full",
    )


@rx.page("/secrets-pki/pki/intermediate-certificates")
@orbitlab_page
def intermediate_certificates_page() -> rx.Component:
    """Render the intermediate certificates management page."""
    return rx.el.div(
        tailwind.PageHeader(
            "Intermediate Signing Certificates",
            tailwind.Buttons.Secondary(
                "Refresh",
                icon="refresh-ccw",
                on_click=IntermediateCertificatesState.cache_clear("all"),
            ),
            tailwind.Buttons.Primary(
                "Create Signing CA",
                icon="plus",
                on_click=tailwind.Dialog.open(CreateIntermediateCADialog.dialog_id),
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
        tailwind.GridList(
            rx.foreach(IntermediateCertificatesState.filtered, lambda ca: IntermediateCertificate(ca)),
        ),
        class_name="w-full h-full",
    )


@rx.page("/secrets-pki/pki/leaf-certificates")
@orbitlab_page
def leaf_certificates_page() -> rx.Component:
    """Render the leaf certificates management page."""
    return rx.el.div(
        tailwind.PageHeader(
            "Leaf Certificates",
            tailwind.Buttons.Secondary(
                "Refresh",
                icon="refresh-ccw",
                on_click=LeafCertificatesState.cache_clear("all"),
            ),
            tailwind.Buttons.Primary(
                "Create Leaf Certificate",
                icon="plus",
                on_click=tailwind.Dialog.open(CreateLeafCertificateDialog.dialog_id),
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
        tailwind.GridList(
            rx.foreach(LeafCertificatesState.filtered, lambda ca: LeafCertificate(ca)),
        ),
        class_name="w-full h-full",
    )
