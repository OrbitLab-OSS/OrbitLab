import json
from base64 import b64encode
from typing import Any, Final

import reflex as rx

from orbitlab.data_types import KeyUsageTypes
from orbitlab.services.pki.client import Certificates
from orbitlab.services.pki.models import Subject
from orbitlab.web.components import Badge, Buttons, CheckboxGroup, Dialog, FieldSet, Input
from orbitlab.web.components.menu import Menu

from .states import CAState, ManageCA


@rx.event
async def revoke_ca(state: ManageCA):
    # TODO: Actually Revoke cert
    state.reset()
    return [
        Dialog.close(ConfirmRevokeCADialog.dialog_id),
        Dialog.close(ManageCertificateAuthorityDialog.dialog_id),
    ]


@rx.event
async def cancel_revoke(state: ManageCA):
    state.revoke_disabled = True
    return Dialog.close(ConfirmRevokeCADialog.dialog_id)


@rx.event
async def ensure_ca_names_match(state: ManageCA, value: str):
    if state.manifest.name == value:
        state.revoke_disabled = False
    else:
        state.revoke_disabled = True


@rx.event
async def create_certificate_authority(state: CAState, form: dict):
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


class CreateCertificateAuthorityDialog:
    dialog_id: Final = "create-certificate-authority-dialog"
    form_id: Final = "create-certificate-authority-form"

    def __new__(cls) -> rx.Component:
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
                on_submit=create_certificate_authority,
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


class ConfirmRevokeCADialog:
    dialog_id: Final = "confirm-revoke-ca-dialog"

    def __new__(cls) -> rx.Component:
        return Dialog(
            f"Revoke {ManageCA.manifest.name}",
            rx.el.div(
                rx.text(
                    "Revoking this Root CA will invalidate all Intermediate CAs and leaf certificates that uses this "
                    "certificate as a trust anchor.",
                ),
                rx.text(
                    "If you are sure you want to revoke ",
                    rx.el.span(ManageCA.manifest.name, class_name="font-bold"),
                    rx.el.span(" type its name below."),
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            Input(
                placeholder=ManageCA.manifest.name,
                on_change=ensure_ca_names_match,
            ),
            rx.el.div(
                Buttons.Secondary("Cancel", on_click=cancel_revoke),
                Buttons.Primary("Confirm", disabled=ManageCA.revoke_disabled, on_click=revoke_ca),
                class_name="w-full flex justify-end space-x-4",
            ),
            dialog_id=cls.dialog_id,
        )


def custom_download(
    url: str | rx.Var | None = None,
    filename: str | rx.Var | None = None,
    data: str | bytes | rx.Var | None = None,
    mime_type: str | rx.Var | None = None,
) -> rx.event.EventSpec:
    """Download the file at a given path or with the specified data.

    Args:
        url: The URL to the file to download.
        filename: The name that the file should be saved as after download.
        data: The data to download.
        mime_type: The mime type of the data to download.

    Raises:
        ValueError: If the URL provided is invalid, both URL and data are provided,
            or the data is not an expected type.

    Returns:
        EventSpec: An event to download the associated file.
    """
    from reflex.components.core.cond import cond

    if isinstance(url, str):
        if not url.startswith("/"):
            msg = "The URL argument should start with a /"
            raise ValueError(msg)

        # if filename is not provided, infer it from url
        if filename is None:
            filename = url.rpartition("/")[-1]

    if filename is None:
        filename = ""

    if data is not None:
        if url is not None:
            msg = "Cannot provide both URL and data to download."
            raise ValueError(msg)

        if isinstance(data, str):
            if mime_type is None:
                mime_type = "text/plain"
            # Caller provided a plain text string to download.
            url = f"data:{mime_type};base64," + b64encode(data.encode("utf-8")).decode(
                "utf-8",
            )
        elif isinstance(data, rx.Var):
            if mime_type is None:
                mime_type = "text/plain"
            # Need to check on the frontend if the Var already looks like a data: URI.

            is_data_url = (data.js_type() == "string") & (data.to(str).startswith("data:"))
            # If it's a data: URI, use it as is, otherwise convert the Var to JSON in a data: URI.
            url = cond(
                is_data_url,
                data.to(str),
                (
                    CREATE_OBJECT_URL.call(create_new_blob(data, mime_type))
                    if isinstance(data, rx.vars.ArrayVar)
                    else f"data:{mime_type};base64,"
                    + BASE64_ENCODE.call(
                        data.to(str) if isinstance(data, rx.vars.StringVar) else data.to_string(),
                    ).to(str)
                ),
            )
        elif isinstance(data, bytes):
            if mime_type is None:
                mime_type = "application/octet-stream"
            # Caller provided bytes, so base64 encode it as a data: URI.
            b64_data = b64encode(data).decode("utf-8")
            url = f"data:{mime_type};base64," + b64_data
        else:
            msg = f"Invalid data type {type(data)} for download. Use `str` or `bytes`."
            raise ValueError(msg)

    return rx.event.server_side(
        "_download",
        rx.event.get_fn_signature(custom_download),
        url=url,
        filename=filename,
    )


BASE64_ENCODE = rx.vars.FunctionStringVar.create(
    "btoa",
    _var_type=rx.vars.function.ReflexCallable[[Any], str],
)
CREATE_OBJECT_URL = rx.vars.FunctionStringVar.create(
    "window.URL.createObjectURL",
    _var_type=rx.vars.function.ReflexCallable[[Any], str],
)


@rx.vars.var_operation
def create_new_blob(data: rx.vars.ArrayVar, mime_type: str):
    return rx.vars.var_operation_return(
        js_expression=f"new Blob([new Uint8Array({data})], {{ type: '{mime_type}' }})",
    )


class ManageCertificateAuthorityDialog:
    dialog_id: Final = "manage-certificate-authority-dialog"

    def __new__(cls) -> rx.Component:
        return Dialog(
            f"Manage {ManageCA.manifest.name}",
            rx.el.div(
                rx.el.div(
                    Buttons.Primary(
                        "Download",
                        icon="download",
                        on_click=custom_download(
                            data=ManageCA.manifest.metadata.certificate,
                            filename=f"{ManageCA.manifest.name.lower().replace(' ', '_')}.crt",
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
                            rx.data_list.value(ManageCA.manifest.metadata.common_name),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Issuer"),
                            rx.data_list.value(
                                rx.cond(
                                    ManageCA.manifest.metadata.common_name == ManageCA.manifest.metadata.issuer,
                                    "Self",
                                    ManageCA.manifest.metadata.issuer,
                                ),
                            ),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Serial Number"),
                            rx.data_list.value(ManageCA.manifest.metadata.serial_number),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organization"),
                            rx.data_list.value(ManageCA.manifest.metadata.org),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Organizational Unit"),
                            rx.data_list.value(ManageCA.manifest.metadata.org_unit),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Country"),
                            rx.data_list.value(ManageCA.manifest.metadata.country),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("State or Province"),
                            rx.data_list.value(ManageCA.manifest.metadata.state_or_province),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Locality"),
                            rx.data_list.value(ManageCA.manifest.metadata.locality),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not Before"),
                            rx.data_list.value(rx.moment(ManageCA.manifest.metadata.not_before)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Not After"),
                            rx.data_list.value(rx.moment(ManageCA.manifest.metadata.not_after)),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Fingerprint"),
                            rx.data_list.value(ManageCA.manifest.metadata.fingerprint),
                        ),
                        rx.data_list.item(
                            rx.data_list.label("Key Usages"),
                            rx.data_list.value(
                                rx.foreach(
                                    ManageCA.manifest.metadata.key_usage,
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
