"""Dialog components for PKI certificate management."""

import json
from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents, KeyUsageTypes
from orbitlab.manifest.secrets import CertificateManifest
from orbitlab.services.pki.client import Certificates
from orbitlab.services.pki.models import IntermediateCA, LeafCertificate, Subject
from orbitlab.web import components
from orbitlab.web.utilities import EventGroup, custom_download

from .states import (
    CertificateAuthoritiesState,
    IntermediateCertificatesState,
    LeafCertificatesState,
    ManageCertificateState,
)


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
        return components.Dialog.close(CreateCertificateAuthorityDialog.dialog_id)

    dialog_id: Final = "create-certificate-authority-dialog"
    form_id: Final = "create-certificate-authority-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
            "Create Certificate Authority",
            rx.el.form(
                components.FieldSet(
                    "Subject",
                    components.FieldSet.Field(
                        "Common Name: ",
                        components.Input(
                            placeholder="My Root CA 1",
                            pattern=r"[A-Za-z0-9_.\-\* ]{1,64}(?:\.[A-Za-z0-9_.\-\* ]{1,64})*",
                            form=cls.form_id,
                            name="common_name",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Organization: ",
                        components.Input(
                            placeholder="My Org",
                            pattern=r"[A-Za-z0-9 .,'()\-_/&]{1,128}",
                            form=cls.form_id,
                            name="org",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Organizational Unit: ",
                        components.Input(
                            placeholder="My Team",
                            pattern=r"[A-Za-z0-9 .,'()\-_/&]{1,128}",
                            form=cls.form_id,
                            name="org_unit",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Country Code (XX): ",
                        components.Input(
                            placeholder="US",
                            pattern=r"[A-Z]{2}",
                            form=cls.form_id,
                            name="country",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "State or Province: ",
                        components.Input(
                            placeholder="Somewhere",
                            pattern=r"[A-Za-z0-9 .,'()\-_/&]{1,128}",
                            form=cls.form_id,
                            name="state_or_province",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Locality: ",
                        components.Input(
                            placeholder="Someplace",
                            pattern=r"[A-Za-z0-9 .,'()\-_/&]{1,128}",
                            form=cls.form_id,
                            name="locality",
                            required=True,
                        ),
                    ),
                ),
                components.FieldSet(
                    "Key Usage",
                    components.FieldSet.Field(
                        "Select All That Apply: ",
                        components.CheckboxGroup(
                            components.CheckboxGroup.Item("Digital Signature", "digital_signature"),
                            components.CheckboxGroup.Item("Key Encipherment", "key_encipherment"),
                            components.CheckboxGroup.Item("Certificate Signing", "key_cert_sign"),
                            components.CheckboxGroup.Item("Data Encipherment", "data_encipherment"),
                            components.CheckboxGroup.Item("CRL Signing", "crl_sign"),
                            components.CheckboxGroup.Item("Content Commitment", "content_commitment"),
                            components.CheckboxGroup.Item("Key Agreement", "key_agreement"),
                            components.CheckboxGroup.Item("Encipher Only", "encipher_only"),
                            components.CheckboxGroup.Item("Decipher Only", "decipher_only"),
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
                components.Buttons.Secondary("Cancel", on_click=lambda: components.Dialog.close(cls.dialog_id)),
                components.Buttons.Primary("Submit", form=cls.form_id),
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
            components.Dialog.close(ConfirmRevokeCADialog.dialog_id),
            components.Dialog.close(ManageCertificateAuthorityDialog.dialog_id),
        ]

    @staticmethod
    @rx.event
    async def cancel_revoke(state: ManageCertificateState) -> FrontendEvents:
        """Cancel the certificate authority revocation process."""
        state.revoke_disabled = True
        return components.Dialog.close(ConfirmRevokeCADialog.dialog_id)

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
        return components.Dialog(
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
            components.Input(
                placeholder=ManageCertificateState.name,
                on_change=cls.ensure_ca_names_match,
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.cancel_revoke),
                components.Buttons.Primary(
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
        return components.Dialog(
            f"Manage {ManageCertificateState.name}",
            rx.el.div(
                rx.el.div(
                    components.Menu(
                        components.Buttons.Primary(
                            "Manage Certificate",
                            icon="chevron-down",
                        ),
                        components.Menu.Item(
                            "Download Certificate",
                            on_click=custom_download(
                                data=ManageCertificateState.certificate_data,
                                filename=f"{ManageCertificateState.name.lower().replace(' ', '_')}.crt",
                                mime_type="application/x-pem-file",
                            ),
                        ),
                        components.Menu.Separator(),
                        components.Menu.Item(
                            "Revoke",
                            on_click=components.Dialog.close(ConfirmRevokeCADialog.dialog_id),
                            class_name="text-red-400 hover:text-red-500 hover:bg-red-500/10 hover:border-red-500/50",
                        ),
                    ),
                    components.Buttons.Secondary(
                        "Close",
                        on_click=components.Dialog.close(cls.dialog_id),
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
                                    lambda usage: components.Badge(usage, color_scheme="blue"),
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
        return components.Dialog.open(CreateIntermediateCADialog.dialog_id)

    dialog_id: Final = "create-intermediate-ca-dialog"
    form_id: Final = "create-intermediate-ca-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
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
                components.FieldSet(
                    "Signing Certificate Configuration",
                    components.FieldSet.Field(
                        "Common Name: ",
                        components.Input(
                            placeholder="My Root CA 1",
                            pattern=r"[A-Za-z0-9_.\-\* ]{1,64}(?:\.[A-Za-z0-9_.\-\* ]{1,64})*",
                            form=cls.form_id,
                            name="common_name",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Root CA: ",
                        components.Select(
                            CertificateAuthoritiesState.names,
                            placeholder="Select Root CA",
                            form=cls.form_id,
                            name="root_ca",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Domain Constraint: ",
                        components.Input(
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
                components.Buttons.Secondary("Cancel", on_click=lambda: components.Dialog.close(cls.dialog_id)),
                components.Buttons.Primary("Submit", form=cls.form_id),
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
        return components.Dialog.close(ConfirmRevokeIntermediateCADialog.dialog_id)

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
            components.Dialog.close(ConfirmRevokeIntermediateCADialog.dialog_id),
            components.Dialog.close(ManageIntermediateCertDialog.dialog_id),
        ]

    dialog_id: Final = "confirm-revoke-intermediate-ca-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
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
            components.Input(
                placeholder=ManageCertificateState.name,
                on_change=cls.ensure_ica_names_match,
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.cancel_revoke),
                components.Buttons.Primary(
                    "Confirm",
                    disabled=ManageCertificateState.revoke_disabled,
                    on_click=cls.revoke_ica,
                ),
                class_name="w-full flex justify-end space-x-4",
            ),
            dialog_id=cls.dialog_id,
        )


class ManageIntermediateCertDialog:
    """Dialog component for managing intermediate certificate authority details."""

    dialog_id: Final = "manage-intermediate-ca-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
            f"Manage {ManageCertificateState.name}",
            rx.el.div(
                rx.el.div(
                    components.Buttons.Primary(
                        "Download",
                        icon="download",
                        on_click=custom_download(
                            data=ManageCertificateState.certificate_data,
                            filename=f"{ManageCertificateState.name.lower().replace(' ', '_')}.crt",
                            mime_type="application/x-pem-file",
                        ),
                    ),
                    components.Buttons.Secondary(
                        "Close",
                        on_click=components.Dialog.close(cls.dialog_id),
                    ),
                    components.Buttons.Secondary(
                        "Revoke",
                        class_name="bg-red-500",
                        on_click=components.Dialog.open(ConfirmRevokeIntermediateCADialog.dialog_id),
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
                                    lambda usage: components.Badge(usage, color_scheme="blue"),
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


class CreateLeafCertificateDialog(EventGroup):
    """Dialog component for creating a new leaf certificate."""

    @staticmethod
    @rx.event(background=True)
    async def create_certificate(state: LeafCertificatesState, form: dict) -> FrontendEvents:
        """Create a new leaf certificate from form data."""
        alternate_dns_names: list[str] = form.get("san_dns", "").split(",")
        alternate_ip_names: list[str] = form.get("san_ips", "").split(",")
        manifest = Certificates().create_leaf_certificate(
            leaf_certificate=LeafCertificate(
                intermediate_ca=form["intermediate_ca"],
                common_name=form["common_name"],
                san_dns=[san.strip() for san in alternate_dns_names if san],
                san_ips=[san.strip() for san in alternate_ip_names if san],
                server_auth="server_auth" in form,
            ),
        )
        async with state:
            state.leaf_certificates.append(manifest)
            state.reset()
        return [
            rx.toast.info(f"Certificate `{manifest.name}` created!"),
            LeafCertificatesState.cache_clear("certificates"),
        ]

    @staticmethod
    @rx.event
    async def create_leaf_cert(_: LeafCertificatesState, form: dict) -> FrontendEvents:
        """Create a new leaf certificate from form data."""
        name = form["common_name"]
        return [
            rx.toast.info(f"Creating certificate `{name}`..."),
            components.Dialog.close(CreateLeafCertificateDialog.dialog_id),
            CreateLeafCertificateDialog.create_certificate(form),
        ]

    dialog_id: Final = "create-leaf-certificate-dialog"
    form_id: Final = "create-leaf-certificate-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
            "Create Leaf Certificate",
            rx.el.form(
                components.FieldSet(
                    "Leaf Certificate Configuration",
                    components.FieldSet.Field(
                        "Common Name: ",
                        components.Input(
                            placeholder="test.example.com",
                            pattern=r"[A-Za-z0-9_.\-\* ]{1,64}(?:\.[A-Za-z0-9_.\-\* ]{1,64})*",
                            form=cls.form_id,
                            name="common_name",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Signing CA: ",
                        components.Select(
                            IntermediateCertificatesState.names,
                            placeholder="Select Signing CA",
                            form=cls.form_id,
                            name="intermediate_ca",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    components.FieldSet.Field(
                        "SAN DNS: ",
                        components.Input(
                            placeholder="test.example.com,*.example.com",
                            form=cls.form_id,
                            name="san_dns",
                        ),
                        description="Comma-separated DNS names",
                    ),
                    components.FieldSet.Field(
                        "SAN IPs: ",
                        components.Input(
                            placeholder="192.168.0.1,172.16.0.1",
                            form=cls.form_id,
                            name="san_ips",
                        ),
                        description="Comma-separated IP addresses",
                    ),
                    components.FieldSet.Field(
                        "Server Auth: ",
                        components.Checkbox(
                            form=cls.form_id,
                            name="server_auth",
                        ),
                        description="Enables Key Encipherment",
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.create_leaf_cert,
                class_name="px-3 overflow-y-auto",
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=lambda: components.Dialog.close(cls.dialog_id)),
                components.Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex justify-end mt-4 space-x-3",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-[50vw] max-h-[75vh] h-[75vh]",
        )


class ManageLeafCertDialog:
    """Dialog component for managing leaf certificate details."""

    dialog_id: Final = "manage-leaf-certificate-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
            f"Manage {ManageCertificateState.name}",
            rx.el.div(
                rx.el.div(
                    components.Menu(
                        components.Buttons.Primary(
                            "Manage Certificate",
                            icon="chevron-down",
                        ),
                        components.Menu.Item(
                            "Download Certificate",
                            on_click=custom_download(
                                data=ManageCertificateState.certificate_data,
                                filename=f"{ManageCertificateState.name.lower().replace(' ', '_')}.crt",
                                mime_type="application/x-pem-file",
                            ),
                        ),
                        components.Menu.Item(
                            "Download Chain",
                            on_click=custom_download(
                                data=ManageCertificateState.certificate_chain_data,
                                filename=f"{ManageCertificateState.name.lower().replace(' ', '_')}-chain.crt",
                                mime_type="application/x-pem-file",
                            ),
                        ),
                        components.Menu.Item(
                            "Download Key",
                            on_click=custom_download(
                                data=ManageCertificateState.key_data,
                                filename=f"{ManageCertificateState.name.lower().replace(' ', '_')}.key",
                                mime_type="application/x-pem-file",
                            ),
                        ),
                        components.Menu.Separator(),
                        components.Menu.Item(
                            "Delete",
                            on_click=components.Dialog.open(ConfirmDeleteLeafCertDialog.dialog_id),
                            class_name="text-red-400 hover:text-red-500 hover:bg-red-500/10 hover:border-red-500/50",
                        ),
                    ),
                    components.Buttons.Secondary(
                        "Close",
                        on_click=components.Dialog.close(cls.dialog_id),
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
                            rx.data_list.label("SANs"),
                            rx.data_list.value(
                                rx.text(ManageCertificateState.dns_sans, rx.el.span(ManageCertificateState.ip_sans)),
                            ),
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
                                    lambda usage: components.Badge(usage, color_scheme="blue"),
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


class ConfirmDeleteLeafCertDialog(EventGroup):
    """Dialog component for confirming the deletion of a leaf certificate."""

    @staticmethod
    @rx.event
    async def cancel(state: ManageCertificateState) -> FrontendEvents:
        """Cancel the leaf certificate deletion process and close the dialog."""
        state.delete_disabled = True
        return components.Dialog.close(ConfirmDeleteLeafCertDialog.dialog_id)

    @staticmethod
    @rx.event
    async def ensure_cert_names_match(state: ManageCertificateState, value: str) -> None:
        """Enable or disable the delete button based on whether the entered name matches the certificate name."""
        state.delete_disabled = state.name != value

    @staticmethod
    @rx.event
    async def delete_cert(state: ManageCertificateState) -> FrontendEvents:
        """Delete the selected leaf certificate and close related dialogs."""
        CertificateManifest.load(name=state.name).delete()
        state.reset()
        return [
            components.Dialog.close(ConfirmDeleteLeafCertDialog.dialog_id),
            components.Dialog.close(ManageLeafCertDialog.dialog_id),
            LeafCertificatesState.cache_clear("certificates"),
        ]

    dialog_id: Final = "confirm-delete-leaf-certificate-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
            f"Delete {ManageCertificateState.name}",
            rx.el.div(
                rx.text(
                    "If you are sure you want to delete leaf certificate ",
                    rx.el.span(ManageCertificateState.name, class_name="font-bold"),
                    rx.el.span(" type its name below."),
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            components.Input(
                placeholder=ManageCertificateState.name,
                on_change=cls.ensure_cert_names_match,
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.cancel),
                components.Buttons.Primary(
                    "Delete",
                    disabled=ManageCertificateState.delete_disabled,
                    on_click=cls.delete_cert,
                ),
                class_name="w-full flex justify-end space-x-4",
            ),
            dialog_id=cls.dialog_id,
        )
