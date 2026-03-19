"""Dialog components for PKI certificate management."""

import json
from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents, KeyUsageTypes
from orbitlab.manifest.pki import (
    IntermediateCertificateManifest,
    LeafCertificateManifest,
    RootCertificateManifest,
    Subject,
)
from orbitlab.web import components
from orbitlab.web.utilities import EventGroup, custom_download, get_worker

from .states import (
    IntermediateCertificatesState,
    ManageIntermediateCertificateState,
    ManageLeafCertificateState,
    ManageRootCertificateState,
    RootCertificatesState,
)


class CreateRootCertificateDialog(EventGroup):
    """Dialog component for creating a new certificate authority."""

    @staticmethod
    @rx.event
    async def create_certificate_authority(_: rx.State, form: dict) -> FrontendEvents:
        """Create a new certificate authority from form data."""
        manifest = RootCertificateManifest.create(
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
        worker = get_worker()
        error = await worker.create_workflow(
            name="pki.create-root",
            version="v1",
            payload={"manifest": manifest.name},
        )
        if error:
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Creating {form['common_name']}..."),
            components.Dialog.close(CreateRootCertificateDialog.dialog_id),
        ]

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
                            auto_complete="root-ca-common-name",
                            form=cls.form_id,
                            name="common_name",
                            required=True,
                            class_name="w-full"
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
                            class_name="w-full"
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
                            class_name="w-full"
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
                            class_name="w-full"
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
                            class_name="w-full"
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
                            class_name="w-full"
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
                class_name="w-full flex justify-end mt-4 space-x-3 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-[50vw] max-h-[75vh] h-[75vh]",
        )


class DeleteRootCertificateDialog(EventGroup):
    """Dialog component for confirming certificate authority deletion."""

    @staticmethod
    @rx.event
    async def delete(state: ManageRootCertificateState) -> FrontendEvents:
        """Delete the certificate authority and close related dialogs."""
        worker = get_worker()
        error = await worker.create_workflow(
            name="pki.delete",
            version="v1",
            payload={"manifest": state.id},
        )
        if error:
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Deleting {state.common_name}..."),
            components.Dialog.close(ManageRootCertificateDialog.dialog_id),
            DeleteRootCertificateDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: ManageRootCertificateState) -> FrontendEvents:
        """Cancel the certificate authority deletion process."""
        state.reset()
        return components.Dialog.close(DeleteRootCertificateDialog.dialog_id)

    @staticmethod
    @rx.event
    async def ensure_ca_names_match(state: ManageRootCertificateState, value: str) -> None:
        """Enable or disable the delete button based on name match."""
        if state.common_name == value:
            state.delete_disabled = False
        else:
            state.delete_disabled = True

    dialog_id: Final = "delete-root-ca-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return components.Dialog(
            f"Revoke {ManageRootCertificateState.common_name}",
            rx.el.div(
                rx.text(
                    "Deleting this Root CA will will not delete and signed Intermediate CAs, but it can no longer be "
                    "used as a trust anchor for new compute instances.",
                ),
                rx.text(
                    "If you are sure you want to delete ",
                    rx.el.span(ManageRootCertificateState.common_name, class_name="font-bold"),
                    rx.el.span(", type its name below."),
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            components.Input(
                placeholder=ManageRootCertificateState.common_name,
                on_change=cls.ensure_ca_names_match,
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.close),
                components.Buttons.Primary(
                    "Confirm",
                    disabled=ManageRootCertificateState.delete_disabled,
                    on_click=cls.delete,
                ),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-fit",
        )


class ManageRootCertificateDialog(EventGroup):
    """Dialog component for managing certificate authority details."""

    @staticmethod
    @rx.event
    async def manage(state: ManageRootCertificateState, name: str) -> FrontendEvents:
        """Load and display the root certificate management dialog."""
        state.manifest = RootCertificateManifest.load(name=name)
        return components.Dialog.open(ManageRootCertificateDialog.dialog_id)

    dialog_id: Final = "manage-certificate-authority-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return components.Dialog(
            f"Manage {ManageRootCertificateState.common_name}",
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
                                data=ManageRootCertificateState.certificate_data,
                                filename=f"{ManageRootCertificateState.download_name}.crt",
                                mime_type="application/x-pem-file",
                            ),
                        ),
                        components.Menu.Separator(),
                        components.Menu.Item(
                            "Delete",
                            on_click=components.Dialog.open(DeleteRootCertificateDialog.dialog_id),
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
                            rx.data_list.value(ManageRootCertificateState.common_name),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Issuer"),
                            rx.data_list.value(ManageRootCertificateState.issuer),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Serial Number"),
                            rx.data_list.value(ManageRootCertificateState.serial_number),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organization"),
                            rx.data_list.value(ManageRootCertificateState.org),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organizational Unit"),
                            rx.data_list.value(ManageRootCertificateState.org_unit),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Country"),
                            rx.data_list.value(ManageRootCertificateState.country),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("State or Province"),
                            rx.data_list.value(ManageRootCertificateState.state_or_province),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Locality"),
                            rx.data_list.value(ManageRootCertificateState.locality),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not Before"),
                            rx.data_list.value(rx.moment(ManageRootCertificateState.not_before)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not After"),
                            rx.data_list.value(rx.moment(ManageRootCertificateState.not_after)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Fingerprint"),
                            rx.data_list.value(ManageRootCertificateState.fingerprint),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Key Usages"),
                            rx.data_list.value(
                                rx.foreach(
                                    ManageRootCertificateState.key_usage,
                                    lambda usage: components.Badge(usage, color_scheme="blue"),
                                ),
                                class_name="flex-wrap",
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
    async def create_intermediate_ca(_: rx.State, form: dict) -> FrontendEvents:
        """Create a new intermediate certificate authority from form data."""
        root_manifest = RootCertificateManifest.load(name=form["root_ca"])
        subject = root_manifest.spec.subject
        subject.common_name = form["common_name"]
        manifest = IntermediateCertificateManifest.create(
            subject=subject,
            root_ca=form["root_ca"],
            domain_constraint=form["domain_constraint"],
        )
        worker = get_worker()
        error = await worker.create_workflow(
            name="pki.create-intermediate",
            version="v1",
            payload={"manifest": manifest.name},
        )
        if error:
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Creating {form['common_name']}..."),
            components.Dialog.close(CreateIntermediateCADialog.dialog_id),
        ]

    dialog_id: Final = "create-intermediate-ca-dialog"
    form_id: Final = "create-intermediate-ca-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
            "Create Intermediate Signing Certificate",
            rx.el.form(
                rx.el.p(
                    (
                        "Select the Root CA to use as the trust anchor for the Intermediate Signing CA. "
                        "The domain constrain specifies what domains the ICA is allowed to issue. Key usage is "
                        "inhereted from the selected trust anchor."
                    ),
                    class_name="my-6",
                ),
                components.FieldSet(
                    "Signing Certificate Configuration",
                    components.FieldSet.Field(
                        "Common Name: ",
                        components.Input(
                            placeholder="My Intermediate CA 1",
                            pattern=r"[A-Za-z0-9_.\-\* ]{1,64}(?:\.[A-Za-z0-9_.\-\* ]{1,64})*",
                            auto_complete="intermediate-ca-common-name",
                            form=cls.form_id,
                            name="common_name",
                            required=True,
                            class_name="w-full"
                        ),
                    ),
                    components.FieldSet.Field(
                        "Root CA: ",
                        components.Select(
                            RootCertificatesState.select_options,
                            placeholder="Select Root CA",
                            form=cls.form_id,
                            name="root_ca",
                            required=True,
                            class_name="w-full"
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
                            class_name="w-full"
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
            class_name="max-w-[50vw] w-[50vw]",
        )


class DeleteIntermediateCertificateDialog(EventGroup):
    """Dialog component for confirming intermediate certificate authority deletion."""

    @staticmethod
    @rx.event
    async def close(state: ManageIntermediateCertificateState) -> FrontendEvents:
        """Cancel the intermediate certificate authority deletion process."""
        state.reset()
        return components.Dialog.close(DeleteIntermediateCertificateDialog.dialog_id)

    @staticmethod
    @rx.event
    async def ensure_ica_names_match(state: ManageIntermediateCertificateState, value: str) -> None:
        """Enable or disable the delete button based on name match."""
        if state.common_name == value:
            state.delete_disabled = False
        else:
            state.delete_disabled = True

    @staticmethod
    @rx.event
    async def delete(state: ManageIntermediateCertificateState) -> FrontendEvents:
        """Delete the intermediate certificate authority and close related dialogs."""
        worker = get_worker()
        error = await worker.create_workflow(
            name="pki.delete",
            version="v1",
            payload={"manifest": state.id},
        )
        if error:
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Deleting {state.common_name}..."),
            components.Dialog.close(ManageIntermediateCertDialog.dialog_id),
            DeleteIntermediateCertificateDialog.close,
        ]

    dialog_id: Final = "confirm-delete-intermediate-ca-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
            f"Delete {ManageIntermediateCertificateState.common_name}",
            rx.el.div(
                rx.text(
                    "Deleting this Root CA will invalidate all Intermediate CAs and leaf certificates that uses this "
                    "certificate as a trust anchor.",
                ),
                rx.text(
                    "If you are sure you want to delete ",
                    rx.el.span(ManageIntermediateCertificateState.common_name, class_name="font-bold"),
                    rx.el.span(" type its name below."),
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            components.Input(
                placeholder=ManageIntermediateCertificateState.common_name,
                on_change=cls.ensure_ica_names_match,
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.close),
                components.Buttons.Primary(
                    "Confirm",
                    disabled=ManageIntermediateCertificateState.delete_disabled,
                    on_click=cls.delete,
                ),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-fit",
        )


class ManageIntermediateCertDialog(EventGroup):
    """Dialog component for managing intermediate certificate authority details."""

    @staticmethod
    @rx.event
    async def manage(state: ManageIntermediateCertificateState, name: str) -> FrontendEvents:
        """Load and display the root certificate management dialog."""
        state.manifest = IntermediateCertificateManifest.load(name=name)
        return components.Dialog.open(ManageIntermediateCertDialog.dialog_id)

    dialog_id: Final = "manage-intermediate-ca-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
            f"Manage {ManageIntermediateCertificateState.common_name}",
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
                                data=ManageIntermediateCertificateState.certificate_data,
                                filename=f"{ManageIntermediateCertificateState.download_name}.crt",
                                mime_type="application/x-pem-file",
                            ),
                        ),
                        components.Menu.Item(
                            "Download Chain",
                            on_click=custom_download(
                                data=ManageIntermediateCertificateState.certificate_chain_data,
                                filename=f"{ManageIntermediateCertificateState.download_name}-chain.crt",
                                mime_type="application/x-pem-file",
                            ),
                        ),
                        components.Menu.Separator(),
                        components.Menu.Item(
                            "Delete",
                            on_click=components.Dialog.open(DeleteIntermediateCertificateDialog.dialog_id),
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
                            rx.data_list.value(ManageIntermediateCertificateState.common_name),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Domain Constraint"),
                            rx.data_list.value(ManageIntermediateCertificateState.domain_constraint),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Issuer"),
                            rx.data_list.value(ManageIntermediateCertificateState.issuer),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Serial Number"),
                            rx.data_list.value(ManageIntermediateCertificateState.serial_number),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organization"),
                            rx.data_list.value(ManageIntermediateCertificateState.org),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organizational Unit"),
                            rx.data_list.value(ManageIntermediateCertificateState.org_unit),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Country"),
                            rx.data_list.value(ManageIntermediateCertificateState.country),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("State or Province"),
                            rx.data_list.value(ManageIntermediateCertificateState.state_or_province),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Locality"),
                            rx.data_list.value(ManageIntermediateCertificateState.locality),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not Before"),
                            rx.data_list.value(rx.moment(ManageIntermediateCertificateState.not_before)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not After"),
                            rx.data_list.value(rx.moment(ManageIntermediateCertificateState.not_after)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Fingerprint"),
                            rx.data_list.value(ManageIntermediateCertificateState.fingerprint),
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
    @rx.event
    async def create_certificate(_: rx.State, form: dict) -> FrontendEvents:
        """Create a new leaf certificate from form data."""
        intermediate_manifest = IntermediateCertificateManifest.load(name=form["intermediate_ca"])
        subject = intermediate_manifest.spec.subject
        subject.common_name = form["common_name"]
        manifest = LeafCertificateManifest.create(
            subject=subject,
            signing_ca=form["intermediate_ca"],
            san_dns=[san.strip() for san in form.get("san_dns", "").split(",") if san],
            san_ips=[san.strip() for san in form.get("san_ips", "").split(",") if san],
            server_auth="server_auth" in form,
        )
        worker = get_worker()
        error = await worker.create_workflow(
            name="pki.create-leaf",
            version="v1",
            payload={"manifest": manifest.name},
        )
        if error:
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Creating {form['common_name']}..."),
            components.Dialog.close(CreateLeafCertificateDialog.dialog_id),
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
                            auto_complete="leaf-cert-common-name",
                            form=cls.form_id,
                            name="common_name",
                            required=True,
                            class_name="w-full"
                        ),
                    ),
                    components.FieldSet.Field(
                        "Signing CA: ",
                        components.Select(
                            IntermediateCertificatesState.select_options,
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
                            class_name="w-full",
                        ),
                        description="Comma-separated DNS names",
                    ),
                    components.FieldSet.Field(
                        "SAN IPs: ",
                        components.Input(
                            placeholder="192.168.0.1,172.16.0.1",
                            form=cls.form_id,
                            name="san_ips",
                            class_name="w-full",
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
                on_submit=cls.create_certificate,
                class_name="px-3 overflow-y-auto",
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=lambda: components.Dialog.close(cls.dialog_id)),
                components.Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex justify-end mt-4 space-x-3 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-[50vw]",
        )


class ManageLeafCertDialog(EventGroup):
    """Dialog component for managing leaf certificate details."""

    @staticmethod
    @rx.event
    async def manage(state: ManageLeafCertificateState, name: str) -> FrontendEvents:
        """Load and display the root certificate management dialog."""
        state.manifest = LeafCertificateManifest.load(name=name)
        return components.Dialog.open(ManageLeafCertDialog.dialog_id)

    dialog_id: Final = "manage-leaf-certificate-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
            f"Manage {ManageLeafCertificateState.common_name}",
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
                                data=ManageLeafCertificateState.certificate_data,
                                filename=f"{ManageLeafCertificateState.download_name}.crt",
                                mime_type="application/x-pem-file",
                            ),
                        ),
                        components.Menu.Item(
                            "Download Chain",
                            on_click=custom_download(
                                data=ManageLeafCertificateState.certificate_chain_data,
                                filename=f"{ManageLeafCertificateState.download_name}-chain.crt",
                                mime_type="application/x-pem-file",
                            ),
                        ),
                        components.Menu.Item(
                            "Download Key",
                            on_click=custom_download(
                                data=ManageLeafCertificateState.key_data,
                                filename=f"{ManageLeafCertificateState.download_name}.key",
                                mime_type="application/x-pem-file",
                            ),
                        ),
                        components.Menu.Separator(),
                        components.Menu.Item(
                            "Delete",
                            on_click=components.Dialog.open(DeleteLeafCertificateDialog.dialog_id),
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
                            rx.data_list.value(ManageLeafCertificateState.common_name),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("SANs"),
                            rx.data_list.value(
                                rx.text(
                                    ManageLeafCertificateState.dns_sans,
                                    rx.el.span(ManageLeafCertificateState.ip_sans),
                                ),
                            ),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Issuer"),
                            rx.data_list.value(ManageLeafCertificateState.issuer),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Serial Number"),
                            rx.data_list.value(ManageLeafCertificateState.serial_number),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organization"),
                            rx.data_list.value(ManageLeafCertificateState.org),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organizational Unit"),
                            rx.data_list.value(ManageLeafCertificateState.org_unit),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Country"),
                            rx.data_list.value(ManageLeafCertificateState.country),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("State or Province"),
                            rx.data_list.value(ManageLeafCertificateState.state_or_province),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Locality"),
                            rx.data_list.value(ManageLeafCertificateState.locality),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not Before"),
                            rx.data_list.value(rx.moment(ManageLeafCertificateState.not_before)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not After"),
                            rx.data_list.value(rx.moment(ManageLeafCertificateState.not_after)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Fingerprint"),
                            rx.data_list.value(ManageLeafCertificateState.fingerprint),
                        ),
                        class_name="max-h-[35vh]",
                    ),
                ),
                class_name="w-full flex md:flex-col justify-center",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-fit max-h-[60vh] h-fit",
        )


class DeleteLeafCertificateDialog(EventGroup):
    """Dialog component for confirming the deletion of a leaf certificate."""

    @staticmethod
    @rx.event
    async def close(state: ManageLeafCertificateState) -> FrontendEvents:
        """Cancel the leaf certificate deletion process and close the dialog."""
        state.reset()
        return components.Dialog.close(DeleteLeafCertificateDialog.dialog_id)

    @staticmethod
    @rx.event
    async def ensure_cert_names_match(state: ManageLeafCertificateState, value: str) -> None:
        """Enable or disable the delete button based on whether the entered name matches the certificate name."""
        state.delete_disabled = state.common_name != value

    @staticmethod
    @rx.event
    async def delete_cert(state: ManageLeafCertificateState) -> FrontendEvents:
        """Delete the selected leaf certificate and close related dialogs."""
        worker = get_worker()
        error = await worker.create_workflow(
            name="pki.delete",
            version="v1",
            payload={"manifest": state.id},
        )
        if error:
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Deleting {state.common_name}..."),
            components.Dialog.close(ManageLeafCertDialog.dialog_id),
            DeleteLeafCertificateDialog.close,
        ]

    dialog_id: Final = "confirm-delete-leaf-certificate-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
            f"Delete {ManageLeafCertificateState.common_name}",
            rx.el.div(
                rx.text(
                    "If you are sure you want to delete leaf certificate ",
                    rx.el.span(ManageLeafCertificateState.common_name, class_name="font-bold"),
                    rx.el.span(" type its name below."),
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            components.Input(
                placeholder=ManageLeafCertificateState.common_name,
                on_change=cls.ensure_cert_names_match,
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.close),
                components.Buttons.Primary(
                    "Delete",
                    disabled=ManageLeafCertificateState.delete_disabled,
                    on_click=cls.delete_cert,
                ),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )
