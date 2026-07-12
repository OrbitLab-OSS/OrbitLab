"""OrbitLab Secrets & PKI Dashboard."""

import reflex as rx

from orbitlab.web import tailwind

from orbitlab.web.global_state import OrbitLabState, OrbitLabStats
from orbitlab.web.layout import orbitlab_page
from .pki.dialogs import CreateLeafCertificateDialog
from .manage_secrets.dialogs import CreateSecretDialog


@rx.page("/secrets-pki")
@orbitlab_page
def secrets_pki_dashboard() -> rx.Component:
    """Render the secrets and PKI management dashboard page."""
    return rx.el.div(
        tailwind.PageHeader(
            "Secrets and PKI Management",
            tailwind.Buttons.Primary(
                "Create Secret",
                icon="plus",
                on_click=tailwind.Dialog.open(CreateSecretDialog.dialog_id),
            ),
            tailwind.Buttons.Primary(
                "Create Leaf Certificate",
                icon="plus",
                on_click=tailwind.Dialog.open(CreateLeafCertificateDialog.dialog_id),
            ),
        ),
        rx.el.div(
            rx.el.div(
                tailwind.Card(
                    rx.el.div(
                        rx.text("Total Count:"),
                        rx.text(OrbitLabState.secrets.length()),
                        class_name="w-full flex justify-between px-6 py-4"
                    ),
                    header=tailwind.Card.Header(rx.text("Secrets", class_name="w-sm")),
                ),
                class_name="col-span-1 h-full",
            ),
            rx.el.div(
                tailwind.Card(
                    rx.el.div(
                        rx.el.div(
                            rx.text("Root:"),
                            rx.text(OrbitLabState.root_certificates.length()),
                            class_name="w-full flex justify-between"
                        ),
                        rx.el.div(
                            rx.text("Intermediate:"),
                            rx.text(OrbitLabState.intermediate_certificates.length()),
                            class_name="w-full flex justify-between"
                        ),
                        rx.el.div(
                            rx.text("Leaf:"),
                            rx.text(OrbitLabState.leaf_certificates.length()),
                            class_name="w-full flex justify-between"
                        ),
                        class_name="w-full flex flex-col px-6 py-4 space-y-2"
                    ),
                    header=tailwind.Card.Header(rx.text("Certificates", class_name="w-sm"))
                ),
                class_name="col-span-1",
            ),
            rx.el.div(
                tailwind.Card(
                    rx.el.div(
                        rx.el.div(
                            rx.text("Root:"),
                            rx.text(OrbitLabStats.certificate_expirations.get("expiring", {}).to(dict).get("root", 0)),
                            class_name="w-full flex justify-between"
                        ),
                        rx.el.div(
                            rx.text("Intermediate:"),
                            rx.text(OrbitLabStats.certificate_expirations.get("expiring", {}).to(dict).get("intermediate", 0)),
                            class_name="w-full flex justify-between"
                        ),
                        rx.el.div(
                            rx.text("Leaf::"),
                            rx.text(OrbitLabStats.certificate_expirations.get("expiring", {}).to(dict).get("leaf", 0)),
                            class_name="w-full flex justify-between"
                        ),
                        class_name="w-full flex flex-col px-6 py-4 space-y-2"
                    ),
                    header=tailwind.Card.Header(rx.text("Certs Expiring (>30 days)", class_name="w-sm"))
                ),
                class_name="col-span-1",
            ),
            rx.el.div(
                tailwind.Card(
                    rx.el.div(
                        rx.el.div(
                            rx.text("Root:"),
                            rx.text(OrbitLabStats.certificate_expirations.get("expired", {}).to(dict).get("root", 0)),
                            class_name="w-full flex justify-between"
                        ),
                        rx.el.div(
                            rx.text("Intermediate:"),
                            rx.text(OrbitLabStats.certificate_expirations.get("expired", {}).to(dict).get("intermediate", 0)),
                            class_name="w-full flex justify-between"
                        ),
                        rx.el.div(
                            rx.text("Leaf::"),
                            rx.text(OrbitLabStats.certificate_expirations.get("expired", {}).to(dict).get("leaf", 0)),
                            class_name="w-full flex justify-between"
                        ),
                        class_name="w-full flex flex-col px-6 py-4 space-y-2"
                    ),
                    header=tailwind.Card.Header(rx.text("Expired Cerificates", class_name="w-sm"))
                ),
                class_name="col-span-1",
            ),
            class_name="w-full grid grid-cols-4 grid-flow-row gap-10 mt-10"
        ),
    )
