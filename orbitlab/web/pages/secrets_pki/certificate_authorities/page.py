from typing import Literal

import reflex as rx

from orbitlab.manifest.schemas.secrets import CertificateManifest
from orbitlab.web.components import Badge, Buttons, GridList, PageHeader
from orbitlab.web.states.managers import DialogStateManager

from .dialogs import ConfirmRevokeCADialog, CreateCertificateAuthorityDialog, ManageCertificateAuthorityDialog
from .states import CAState, ManageCA


@rx.event
async def set_ca_filter(state: CAState, ca_filter: Literal["All", "Valid", "Warning", "Expired"]):
    state.ca_filter = ca_filter


@rx.event
async def manage_root_ca(state: ManageCA, ca: dict):
    state.manifest = CertificateManifest.model_validate(ca)
    return DialogStateManager.toggle(ManageCertificateAuthorityDialog.dialog_id)


class CertificateAuthorities:
    @classmethod
    def __ca__(cls, ca: CertificateManifest) -> rx.Component:
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
            on_click=lambda: manage_root_ca(ca),
            class_name="cursor-pointer",
        )

    @classmethod
    def __filter_button__(cls, label: str) -> rx.Component:
        return rx.el.button(
            label,
            on_click=lambda: set_ca_filter(label),
            data_active=CAState.ca_filter == label,
            class_name=(
                "flex items-start px-3 py-2.5 rounded-xl data-[active=true]:bg-sky-100 "
                "data-[active=true]:text-sky-600 data-[active=true]:dark:bg-sky-900/50 "
                "data-[active=true]:dark:text-sky-300 data-[active=false]:text-gray-500 "
                "data-[active=false]:dark:text-gray-400 "
                "data-[active=false]:hover:bg-gray-100 data-[active=false]:dark:hover:bg-gray-800 "
                "data-[active=false]:hover:text-gray-800 data-[active=false]:dark:hover:text-gray-200"
            ),
        )

    def __new__(cls):
        return rx.el.div(
            PageHeader(
                "Certificate Authority Management",
                Buttons.Primary(
                    "Create CA",
                    icon="plus",
                    on_click=DialogStateManager.toggle(CreateCertificateAuthorityDialog.dialog_id),
                ),
            ),
            CreateCertificateAuthorityDialog(),
            ManageCertificateAuthorityDialog(),
            ConfirmRevokeCADialog(),
            rx.el.div(
                cls.__filter_button__("All"),
                cls.__filter_button__("Valid"),
                cls.__filter_button__("Warning"),
                cls.__filter_button__("Expired"),
                class_name="flex items-center gap-2 mb-8",
            ),
            GridList(
                rx.foreach(
                    CAState.filtered_cas,
                    lambda ca: cls.__ca__(ca),
                ),
            ),
            class_name="w-full h-full",
        )
