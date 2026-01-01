"""Dialog components for PKI certificate management."""

import json
from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents, KeyUsageTypes
from orbitlab.services.pki.client import Certificates
from orbitlab.services.pki.models import IntermediateCA, Subject
from orbitlab.web.components import Badge, Buttons, CheckboxGroup, Dialog, FieldSet, Input, Select
from orbitlab.web.components.menu import Menu
from orbitlab.web.utilities import EventGroup, custom_download

from .states import CertificateAuthoritiesState, IntermediateCertificatesState, ManageCertificateState


class CreateCertificateAuthorityDialog(EventGroup):
    """Dialog component for creating a new certificate authority."""

    @staticmethod
    @rx.event
    async def create_certificate_authority(state: CertificateAuthoritiesState, form: dict) -> FrontendEvents:
        """Create a new certificate authority from form data."""
        manifest = Certificates().create_certificate_authority(
            subject=Subject(
                common_name=form["common_name"],
                org=form["org"],
                org_unit=form["org_unit"],
                country=form["country"],
                state_or_province=form["state_or_province"],
                locality=form["locality"],
            ),
            key_usage=[KeyUsageTypes(usage) for usage in json.loads(form["key_usage"])],
        )
        state.certificate_authorities.append(manifest)
        return Dialog.close(CreateCertificateAuthorityDialog.dialog_id)

    dialog_id: Final = "create-certificate-authority-dialog"
    form_id: Final = "create-certificate-authority-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return Dialog(
            "Create Certificate Authority",
            rx.el.form(
                FieldSet(
                    "Subject",
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
                        "Organization: ",
                        Input(
                            placeholder="My Org",
                            pattern=r"[A-Za-z0-9 .,'()\-_/&]{1,128}",
                            form=cls.form_id,
                            name="org",
                            required=True,
                        ),
                    ),
                    FieldSet.Field(
                        "Organizational Unit: ",
                        Input(
                            placeholder="My Team",
                            pattern=r"[A-Za-z0-9 .,'()\-_/&]{1,128}",
                            form=cls.form_id,
                            name="org_unit",
                            required=True,
                        ),
                    ),
                    FieldSet.Field(
                        "Country Code (XX): ",
                        Input(
                            placeholder="US",
                            pattern=r"[A-Z]{2}",
                            form=cls.form_id,
                            name="country",
                            required=True,
                        ),
                    ),
                    FieldSet.Field(
                        "State or Province: ",
                        Input(
                            placeholder="Somewhere",
                            pattern=r"[A-Za-z0-9 .,'()\-_/&]{1,128}",
                            form=cls.form_id,
                            name="state_or_province",
                            required=True,
                        ),
                    ),
                    FieldSet.Field(
                        "Locality: ",
                        Input(
                            placeholder="Someplace",
                            pattern=r"[A-Za-z0-9 .,'()\-_/&]{1,128}",
                            form=cls.form_id,
                            name="locality",
                            required=True,
                        ),
                    ),
                ),
                FieldSet(
                    "Key Usage",
                    FieldSet.Field(
                        "Select All That Apply: ",
                        CheckboxGroup(
                            CheckboxGroup.Item("Digital Signature", "digital_signature"),
                            CheckboxGroup.Item("Key Encipherment", "key_encipherment"),
                            CheckboxGroup.Item("Certificate Signing", "key_cert_sign"),
                            CheckboxGroup.Item("Data Encipherment", "data_encipherment"),
                            CheckboxGroup.Item("CRL Signing", "crl_sign"),
                            CheckboxGroup.Item("Content Commitment", "content_commitment"),
                            CheckboxGroup.Item("Key Agreement", "key_agreement"),
                            CheckboxGroup.Item("Encipher Only", "encipher_only"),
                            CheckboxGroup.Item("Decipher Only", "decipher_only"),
                            form=cls.form_id,
                            name="key_usage",
                            required=True,
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.create_certificate_authority,
                class_name="px-3 overflow-y-auto",
            ),
            rx.el.div(
                Buttons.Secondary("Cancel", on_click=lambda: Dialog.close(cls.dialog_id)),
                Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex justify-end mt-4 space-x-3",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-[50vw] max-h-[75vh] h-[75vh]",
        )


class ConfirmRevokeCADialog(EventGroup):
    """Dialog component for confirming certificate authority revocation."""

    @staticmethod
    @rx.event
    async def revoke_ca(state: ManageCertificateState) -> FrontendEvents:
        """Revoke the certificate authority and close related dialogs."""
        # TODO: Actually Revoke cert
        state.reset()
        return [
            Dialog.close(ConfirmRevokeCADialog.dialog_id),
            Dialog.close(ManageCertificateAuthorityDialog.dialog_id),
        ]

    @staticmethod
    @rx.event
    async def cancel_revoke(state: ManageCertificateState) -> FrontendEvents:
        """Cancel the certificate authority revocation process."""
        state.revoke_disabled = True
        return Dialog.close(ConfirmRevokeCADialog.dialog_id)

    @staticmethod
    @rx.event
    async def ensure_ca_names_match(state: ManageCertificateState, value: str) -> None:
        """Enable or disable the revoke button based on name match."""
        if state.manifest.name == value:
            state.revoke_disabled = False
        else:
            state.revoke_disabled = True

    dialog_id: Final = "confirm-revoke-ca-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return Dialog(
            f"Revoke {ManageCertificateState.name}",
            rx.el.div(
                rx.text(
                    "Revoking this Root CA will invalidate all Intermediate CAs and leaf certificates that uses this "
                    "certificate as a trust anchor.",
                ),
                rx.text(
                    "If you are sure you want to revoke ",
                    rx.el.span(ManageCertificateState.name, class_name="font-bold"),
                    rx.el.span(" type its name below."),
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            Input(
                placeholder=ManageCertificateState.name,
                on_change=cls.ensure_ca_names_match,
            ),
            rx.el.div(
                Buttons.Secondary("Cancel", on_click=cls.cancel_revoke),
                Buttons.Primary(
                    "Confirm",
                    disabled=ManageCertificateState.revoke_disabled,
                    on_click=cls.revoke_ca,
                ),
                class_name="w-full flex justify-end space-x-4",
            ),
            dialog_id=cls.dialog_id,
        )


class ManageCertificateAuthorityDialog:
    """Dialog component for managing certificate authority details."""

    dialog_id: Final = "manage-certificate-authority-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return Dialog(
            f"Manage {ManageCertificateState.name}",
            rx.el.div(
                rx.el.div(
                    Buttons.Primary(
                        "Download",
                        icon="download",
                        on_click=custom_download(
                            data=ManageCertificateState.certificate_data,
                            filename=f"{ManageCertificateState.name.lower().replace(' ', '_')}.crt",
                            mime_type="application/x-pem-file",
                        ),
                    ),
                    Buttons.Secondary(
                        "Close",
                        on_click=Dialog.close(cls.dialog_id),
                    ),
                    Menu(
                        Buttons.Secondary("Danger", icon="chevron-down", class_name="bg-red-600/80"),
                        Menu.Item(
                            "Revoke",
                            on_click=Dialog.close(ConfirmRevokeCADialog.dialog_id),
                            class_name="text-red-400 hover:text-red-500 hover:bg-red-500/10 hover:border-red-500/50",
                        ),
                    ),
                    class_name="w-full flex justify-end space-x-4 my-4",
                ),
                rx.scroll_area(
                    rx.data_list.root(
                        rx.data_list.item(
                            rx.data_list.label("Common Name"),
                            rx.data_list.value(ManageCertificateState.common_name),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Issuer"),
                            rx.data_list.value(ManageCertificateState.issuer),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Serial Number"),
                            rx.data_list.value(ManageCertificateState.serial_number),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organization"),
                            rx.data_list.value(ManageCertificateState.org),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organizational Unit"),
                            rx.data_list.value(ManageCertificateState.org_unit),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Country"),
                            rx.data_list.value(ManageCertificateState.country),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("State or Province"),
                            rx.data_list.value(ManageCertificateState.state_or_province),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Locality"),
                            rx.data_list.value(ManageCertificateState.locality),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not Before"),
                            rx.data_list.value(rx.moment(ManageCertificateState.not_before)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not After"),
                            rx.data_list.value(rx.moment(ManageCertificateState.not_after)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Fingerprint"),
                            rx.data_list.value(ManageCertificateState.fingerprint),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Key Usages"),
                            rx.data_list.value(
                                rx.foreach(
                                    ManageCertificateState.key_usage,
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


class CreateIntermediateCADialog(EventGroup):
    """Dialog component for creating a new intermediate certificate authority."""

    @staticmethod
    @rx.event
    async def create_intermediate_ca(state: IntermediateCertificatesState, form: dict) -> FrontendEvents:
        """Create a new intermediate certificate authority from form data."""
        manifest = Certificates().create_intermediate_certificate(
            IntermediateCA(
                common_name=form["common_name"],
                root_ca=form["root_ca"],
                domain_constraint=form["domain_constraint"],
            ),
        )
        state.intermediate_certificates.append(manifest)
        return Dialog.open(CreateIntermediateCADialog.dialog_id)

    dialog_id: Final = "create-intermediate-ca-dialog"
    form_id: Final = "create-intermediate-ca-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
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
                            CertificateAuthoritiesState.names,
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
                on_submit=cls.create_intermediate_ca,
                class_name="px-3 overflow-y-auto",
            ),
            rx.el.div(
                Buttons.Secondary("Cancel", on_click=lambda: Dialog.close(cls.dialog_id)),
                Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex justify-end mt-4 space-x-3",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-[50vw] max-h-[75vh] h-[75vh]",
        )


class ConfirmRevokeIntermediateCADialog(EventGroup):
    """Dialog component for confirming intermediate certificate authority revocation."""

    @staticmethod
    @rx.event
    async def cancel_revoke(state: ManageCertificateState) -> FrontendEvents:
        """Cancel the intermediate certificate authority revocation process."""
        state.revoke_disabled = True
        return Dialog.close(ConfirmRevokeIntermediateCADialog.dialog_id)

    @staticmethod
    @rx.event
    async def ensure_ica_names_match(state: ManageCertificateState, value: str) -> None:
        """Enable or disable the revoke button based on name match."""
        if state.name == value:
            state.revoke_disabled = False
        else:
            state.revoke_disabled = True

    @staticmethod
    @rx.event
    async def revoke_ica(state: ManageCertificateState) -> FrontendEvents:
        """Revoke the intermediate certificate authority and close related dialogs."""
        # TODO: Actually Revoke cert
        state.reset()
        return [
            Dialog.close(ConfirmRevokeIntermediateCADialog.dialog_id),
            Dialog.close(ManageIntermediateCertDialog.dialog_id),
        ]

    dialog_id: Final = "confirm-revoke-intermediate-ca-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return Dialog(
            f"Revoke {ManageCertificateState.name}",
            rx.el.div(
                rx.text(
                    "Revoking this Root CA will invalidate all Intermediate CAs and leaf certificates that uses this "
                    "certificate as a trust anchor.",
                ),
                rx.text(
                    "If you are sure you want to revoke ",
                    rx.el.span(ManageCertificateState.name, class_name="font-bold"),
                    rx.el.span(" type its name below."),
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            Input(
                placeholder=ManageCertificateState.name,
                on_change=cls.ensure_ica_names_match,
            ),
            rx.el.div(
                Buttons.Secondary("Cancel", on_click=cls.cancel_revoke),
                Buttons.Primary("Confirm", disabled=ManageCertificateState.revoke_disabled, on_click=cls.revoke_ica),
                class_name="w-full flex justify-end space-x-4",
            ),
            dialog_id=cls.dialog_id,
        )


class ManageIntermediateCertDialog:
    """Dialog component for managing intermediate certificate authority details."""

    dialog_id: Final = "manage-intermediate-ca-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return Dialog(
            f"Manage {ManageCertificateState.name}",
            rx.el.div(
                rx.el.div(
                    Buttons.Primary(
                        "Download",
                        icon="download",
                        on_click=custom_download(
                            data=ManageCertificateState.certificate_data,
                            filename=f"{ManageCertificateState.name.lower().replace(' ', '_')}.crt",
                            mime_type="application/x-pem-file",
                        ),
                    ),
                    Buttons.Secondary(
                        "Close",
                        on_click=Dialog.close(cls.dialog_id),
                    ),
                    Buttons.Secondary(
                        "Revoke",
                        class_name="bg-red-500",
                        on_click=Dialog.open(ConfirmRevokeIntermediateCADialog.dialog_id),
                    ),
                    class_name="w-full flex justify-end space-x-4 my-4",
                ),
                rx.scroll_area(
                    rx.data_list.root(
                        rx.data_list.item(
                            rx.data_list.label("Common Name"),
                            rx.data_list.value(ManageCertificateState.common_name),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Domain Constraint"),
                            rx.data_list.value(ManageCertificateState.domain_constraint),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Issuer"),
                            rx.data_list.value(
                                rx.cond(
                                    ManageCertificateState.common_name
                                    == ManageCertificateState.issuer,
                                    "Self",
                                    ManageCertificateState.issuer,
                                ),
                            ),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Serial Number"),
                            rx.data_list.value(ManageCertificateState.serial_number),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organization"),
                            rx.data_list.value(ManageCertificateState.org),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organizational Unit"),
                            rx.data_list.value(ManageCertificateState.org_unit),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Country"),
                            rx.data_list.value(ManageCertificateState.country),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("State or Province"),
                            rx.data_list.value(ManageCertificateState.state_or_province),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Locality"),
                            rx.data_list.value(ManageCertificateState.locality),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not Before"),
                            rx.data_list.value(rx.moment(ManageCertificateState.not_before)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not After"),
                            rx.data_list.value(rx.moment(ManageCertificateState.not_after)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Fingerprint"),
                            rx.data_list.value(ManageCertificateState.fingerprint),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Key Usages"),
                            rx.data_list.value(
                                rx.foreach(
                                    ManageCertificateState.key_usage,
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
