from typing import Final

import reflex as rx

from orbitlab.services.pki.client import Certificates
from orbitlab.services.pki.models import IntermediateCA
from orbitlab.web.components import Badge, Buttons, Dialog, FieldSet, Input
from orbitlab.web.components.select import Select
from orbitlab.web.states.managers import DialogStateManager

from .states import IntermediateCAState, ManageIntermediateCerts


@rx.event
async def revoke_ica(state: ManageIntermediateCerts):
    # TODO: Actually Revoke cert
    state.reset()
    return [
        DialogStateManager.toggle(ConfirmRevokeIntermediateCADialog.dialog_id),
        DialogStateManager.toggle(ManageIntermediateCertDialog.dialog_id),
    ]


@rx.event
async def cancel_revoke(state: ManageIntermediateCerts):
    state.revoke_disabled = True
    return DialogStateManager.toggle(ConfirmRevokeIntermediateCADialog.dialog_id)


@rx.event
async def ensure_ica_names_match(state: ManageIntermediateCerts, value: str):
    if state.manifest.name == value:
        state.revoke_disabled = False
    else:
        state.revoke_disabled = True


@rx.event
async def create_intermediate_ca(state: IntermediateCAState, form: dict):
    manifest = Certificates().create_intermediate_certificate(
        IntermediateCA(
            common_name=form["common_name"],
            root_ca=form["root_ca"],
            domain_constraint=form["domain_constraint"],
        ),
    )
    state.intermediate_certificates.append(manifest)
    return DialogStateManager.toggle(CreateIntermediateCADialog.dialog_id)


class CreateIntermediateCADialog:
    dialog_id: Final = "create-intermediate-ca-dialog"
    form_id: Final = "create-intermediate-ca-form"

    def __new__(cls) -> rx.Component:
        return Dialog(
            "Create Intermediate Signing Certificate",
            rx.el.form(
                rx.el.p(
                    "Select the Root CA to use as the trust anchor for the Intermediate Signing CA.",
                    class_name="my-6",
                ),
                rx.el.p(
                    "The domain constrain specifies what domains the ICA is allowed to issue.",
                    class_name="my-6",
                ),
                FieldSet(
                    "Signing Certificate Configuration",
                    FieldSet.Field(
                        "Common Name: ",
                        Input(
                            placeholder="My Root CA 1",
                            pattern=r"[A-Za-z0-9_.\-\* ]{1,64}(?:\.[A-Za-z0-9_.\-\* ]{1,64})*",
                            form=cls.form_id,
                            name="common_name",
                            required=True,
                        ),
                    ),
                    FieldSet.Field(
                        "Root CA: ",
                        Select(
                            IntermediateCAState.root_certificates,
                            placeholder="Select Root CA",
                            form=cls.form_id,
                            name="root_ca",
                            required=True,
                        ),
                    ),
                    FieldSet.Field(
                        "Domain Constraint: ",
                        Input(
                            placeholder="example.com",
                            pattern=r"(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}",
                            form=cls.form_id,
                            name="domain_constraint",
                            required=True,
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=create_intermediate_ca,
                class_name="px-3 overflow-y-auto",
            ),
            rx.el.div(
                Buttons.Secondary("Cancel", on_click=lambda: DialogStateManager.toggle(cls.dialog_id)),
                Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex justify-end mt-4 space-x-3",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-[50vw] max-h-[75vh] h-[75vh]",
        )


class ConfirmRevokeIntermediateCADialog:
    dialog_id: Final = "confirm-revoke-intermediate-ca-dialog"

    def __new__(cls) -> rx.Component:
        return Dialog(
            f"Revoke {ManageIntermediateCerts.manifest.name}",
            rx.el.div(
                rx.text(
                    "Revoking this Root CA will invalidate all Intermediate CAs and leaf certificates that uses this "
                    "certificate as a trust anchor.",
                ),
                rx.text(
                    "If you are sure you want to revoke ",
                    rx.el.span(ManageIntermediateCerts.manifest.name, class_name="font-bold"),
                    rx.el.span(" type its name below."),
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            Input(
                placeholder=ManageIntermediateCerts.manifest.name,
                on_change=ensure_ica_names_match,
            ),
            rx.el.div(
                Buttons.Secondary("Cancel", on_click=cancel_revoke),
                Buttons.Primary("Confirm", disabled=ManageIntermediateCerts.revoke_disabled, on_click=revoke_ica),
                class_name="w-full flex justify-end space-x-4",
            ),
            dialog_id=cls.dialog_id,
        )


class ManageIntermediateCertDialog:
    dialog_id: Final = "manage-intermediate-ca-dialog"

    def __new__(cls) -> rx.Component:
        return Dialog(
            f"Manage {ManageIntermediateCerts.manifest.name}",
            rx.el.div(
                rx.el.div(
                    Buttons.Primary(
                        "Download",
                        icon="download",
                    ),
                    Buttons.Secondary(
                        "Close",
                        on_click=DialogStateManager.toggle(cls.dialog_id),
                    ),
                    Buttons.Secondary(
                        "Revoke",
                        class_name="bg-red-500",
                        on_click=DialogStateManager.toggle(ConfirmRevokeIntermediateCADialog.dialog_id),
                    ),
                    class_name="w-full flex justify-end space-x-4 my-4",
                ),
                rx.scroll_area(
                    rx.data_list.root(
                        rx.data_list.item(
                            rx.data_list.label("Common Name"),
                            rx.data_list.value(ManageIntermediateCerts.manifest.metadata.common_name),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Domain Constraint"),
                            rx.data_list.value(ManageIntermediateCerts.manifest.metadata.domain_constraint),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Issuer"),
                            rx.data_list.value(
                                rx.cond(
                                    ManageIntermediateCerts.manifest.metadata.common_name
                                    == ManageIntermediateCerts.manifest.metadata.issuer,
                                    "Self",
                                    ManageIntermediateCerts.manifest.metadata.issuer,
                                ),
                            ),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Serial Number"),
                            rx.data_list.value(ManageIntermediateCerts.manifest.metadata.serial_number),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organization"),
                            rx.data_list.value(ManageIntermediateCerts.manifest.metadata.org),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organizational Unit"),
                            rx.data_list.value(ManageIntermediateCerts.manifest.metadata.org_unit),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Country"),
                            rx.data_list.value(ManageIntermediateCerts.manifest.metadata.country),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("State or Province"),
                            rx.data_list.value(ManageIntermediateCerts.manifest.metadata.state_or_province),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Locality"),
                            rx.data_list.value(ManageIntermediateCerts.manifest.metadata.locality),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not Before"),
                            rx.data_list.value(rx.moment(ManageIntermediateCerts.manifest.metadata.not_before)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not After"),
                            rx.data_list.value(rx.moment(ManageIntermediateCerts.manifest.metadata.not_after)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Fingerprint"),
                            rx.data_list.value(ManageIntermediateCerts.manifest.metadata.fingerprint),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Key Usages"),
                            rx.data_list.value(
                                rx.foreach(
                                    ManageIntermediateCerts.manifest.metadata.key_usage,
                                    lambda usage: Badge(usage, color_scheme="blue"),
                                ),
                            ),
                        ),
                        class_name="max-h-[35vh]",
                    ),
                ),
                class_name="w-full flex md:flex-col justify-center",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-fit max-h-[60vh] h-fit",
        )
