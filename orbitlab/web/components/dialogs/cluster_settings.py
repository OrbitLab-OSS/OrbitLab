import json
from typing import Final

import reflex as rx

from orbitlab.data_types import DomainValidationProviders, FrontendEvents, StorageContentType
from orbitlab.redis.clients import ClusterClient, SecretsClient
from orbitlab.redis.models import Defaults, DomainProvider
from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState, SelectOptions, SelectionDefaults
from orbitlab.web.utilities import EventGroup


class AddDomainProviderDialogState(rx.State):
    provider: rx.Field[str] = rx.field(default="")


class AddDomainProviderDialog(EventGroup):
    
    @staticmethod
    @rx.event
    async def open(state: AddDomainProviderDialogState) -> FrontendEvents:
        state.reset()
        return tailwind.Dialog.open(AddDomainProviderDialog.dialog_id)
    
    @staticmethod
    @rx.event
    async def select_provider(state: AddDomainProviderDialogState, provider: str) -> None:
        state.provider = provider
    
    @staticmethod
    @rx.event
    async def add_provider(_: rx.State, form: dict) -> FrontendEvents:
        client = ClusterClient()
        if await client.domain_provider_exists(name=form["name"]):
            return rx.toast.error(f"A Domain Provider named '{form['name']}' already exists.")
        
        credentials = {}
        for key in form:
            if str(key).startswith("credentials."):
                credentials[str(key).replace("credentials.", "")] = form[key]
                
        secret = await SecretsClient().create_service_secret(service_name="domain_provider", service_id=form["name"], value=json.dumps(credentials))
        form["credentials"] = secret.name
        domain_provider = DomainProvider.model_validate(form)
        await client.add_domain_provider(domain_provider=domain_provider)
        return [
            OrbitLabState.cache_clear("domain_providers"),
            AddDomainProviderDialog.close,
            rx.toast.success(f"Created Domain Provider '{form['name']}'."),
        ]
    
    @staticmethod
    @rx.event
    async def close(state: AddDomainProviderDialogState) -> FrontendEvents:
        state.reset()
        return tailwind.Dialog.close(AddDomainProviderDialog.dialog_id)
    
    dialog_id: Final = "cluster-add-domain-provider-dialog"
    form_id: Final = "cluster-add-domain-provider-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return tailwind.Dialog(
            "Add Domain Provider",
            rx.el.div(
                rx.el.form(
                    tailwind.FieldSet(
                        "Domain Provider",
                        tailwind.FieldSet.Field(
                            "Name: ",
                            tailwind.Input(
                                placeholder="My Provider",
                                auto_complete="off",
                                name="name",
                                form=cls.form_id,
                                required=True,
                                class_name="w-full"
                            ),
                        ),
                        tailwind.FieldSet.Field(
                            "Provider:",
                            tailwind.Select(
                                SelectOptions.domain_validation_provider_options,
                                placeholder="Select Provider",
                                on_change=cls.select_provider,
                                name="provider",
                                form=cls.form_id,
                                required=True,
                                class_name="w-full"
                            ),
                            description="Public DNS Provider",
                        ),
                        tailwind.FieldSet.Field(
                            "Email:",
                            tailwind.Input(
                                type="email",
                                pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
                                error="Enter a valid email address",
                                placeholder="me@example.com",
                                auto_complete="acme-email",
                                name="email",
                                form=cls.form_id,
                                required=True,
                                class_name="w-full"
                            ),
                            description="For Notifications",
                        ),
                        tailwind.FieldSet.Field(
                            "Credentials:",
                            rx.fragment(
                                rx.match(
                                    AddDomainProviderDialogState.provider,
                                    (
                                        DomainValidationProviders.CLOUDFLARE,
                                        tailwind.Input(
                                            type="password",
                                            placeholder="Cloudflare API Token",
                                            auto_complete="off",
                                            name="credentials.CF_DNS_API_TOKEN",
                                            form=cls.form_id,
                                            required=True,
                                            class_name="w-full"
                                        ),
                                    ),
                                    rx.text(
                                        "Select a Provider",
                                        class_name="w-full flex items-center justify-center opacity-50 text-sm italic",
                                    )
                                ),
                            ),
                        ),
                    ),
                    id=cls.form_id,
                    on_submit=cls.add_provider
                ),
                rx.el.div(
                    tailwind.Buttons.Secondary("Close", on_click=cls.close),
                    tailwind.Buttons.Primary("Submit", form=cls.form_id),
                    class_name="w-full flex items-center justify-end space-x-2"
                ),
                class_name="w-full flex flex-col"
            ),
            dialog_id=cls.dialog_id,
            class_name="w-[33vw] h-fit",
        )


class UpdateDomainProviderCredentialDialogState(rx.State):
    domain_provider: rx.Field[DomainProvider | None] = rx.field(default=None)


class UpdateDomainProviderCredentialDialog(EventGroup):
    
    @staticmethod
    @rx.event
    async def open(state: UpdateDomainProviderCredentialDialogState, name: str) -> FrontendEvents:
        state.domain_provider = await ClusterClient().get_domain_provider(name=name)
        return tailwind.Dialog.open(UpdateDomainProviderCredentialDialog.dialog_id)
    
    @staticmethod
    @rx.event
    async def add_provider(_: rx.State, form: dict) -> FrontendEvents:
        credentials = {}
        for key in form:
            if str(key).startswith("credentials."):
                credentials[str(key).replace("credentials.", "")] = form[key]
                
        await SecretsClient().update_service_secret(service_name="domain_provider", service_id=form["name"], value=json.dumps(credentials))
        return [
            OrbitLabState.cache_clear("domain_providers"),
            UpdateDomainProviderCredentialDialog.close,
            rx.toast.success(f"Updated domain provider '{form['name']}' credentials."),
        ]
    
    @staticmethod
    @rx.event
    async def close(state: UpdateDomainProviderCredentialDialogState) -> FrontendEvents:
        state.reset()
        return tailwind.Dialog.close(UpdateDomainProviderCredentialDialog.dialog_id)
    
    dialog_id: Final = "cluster-update-domain-provider-credential-dialog"
    form_id: Final = "cluster-update-domain-provider-credential-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return tailwind.Dialog(
            f"Update {UpdateDomainProviderCredentialDialogState.domain_provider.name} Credentials",
            rx.el.div(
                rx.el.form(
                    rx.match(
                        AddDomainProviderDialogState.provider,
                        (
                            DomainValidationProviders.CLOUDFLARE,
                            tailwind.Input(
                                type="password",
                                placeholder="Cloudflare API Token",
                                auto_complete="off",
                                name="credentials.CF_DNS_API_TOKEN",
                                form=cls.form_id,
                                required=True,
                                class_name="w-full"
                            ),
                        ),
                        rx.text("Unknown Provider", class_name="w-full flex items-center justify-center opacity-50 text-sm italic")
                    ),
                    id=cls.form_id,
                    on_submit=cls.add_provider
                ),
                rx.el.div(
                    tailwind.Buttons.Secondary("Close", on_click=cls.close),
                    tailwind.Buttons.Primary("Submit", form=cls.form_id),
                    class_name="w-full flex items-center justify-end space-x-2"
                ),
                class_name="w-full flex flex-col"
            ),
            dialog_id=cls.dialog_id,
            class_name="w-[33vw] h-fit",
        )


class DomainProviderseTable(tailwind.Table):
    
    @classmethod
    def row(cls, domain_provider: DomainProvider) -> list[rx.Component]:
        """Create and return the table row component."""
        return [
            rx.text(domain_provider.name),
            tailwind.Badge(domain_provider.provider.upper(), color_scheme="blue"),
            tailwind.Badge(domain_provider.email.lower()),
            tailwind.Menu(
                tailwind.Buttons.Icon("ellipsis-vertical"),
                tailwind.Menu.Item(
                    "Update Credential",
                    on_click=UpdateDomainProviderCredentialDialog.open(domain_provider.name),
                ),
            ),
        ]


class ClusterSettingsDialogState(rx.State):
    """State for the Cluster Settings Dialog."""

    initializing: rx.Field[bool] = rx.field(default=False)
    defaults: rx.Field[Defaults | None] = rx.field(default=None)
    color_mode: rx.Field[str] = rx.field(default="system")
    
    @rx.event
    async def initalize(self) -> FrontendEvents:
        self.reset()
        self.initializing = True
        return ClusterSettingsDialog.open


class ClusterSettingsDialog(EventGroup):
    """Dialog component for managing cluster settings in the OrbitLab web application."""

    @staticmethod
    @rx.event
    async def open(state: ClusterSettingsDialogState) -> FrontendEvents:
        state.defaults = await state.get_var_value(SelectionDefaults.defaults)
        return tailwind.Dialog.open(ClusterSettingsDialog.dialog_id)

    @staticmethod
    @rx.event
    async def on_submit(state: ClusterSettingsDialogState) -> FrontendEvents | None:
        if state.defaults is not None:
            if missing := state.defaults.valid():
                return rx.toast.error(f"A default {missing.capitalize()} must be selected.")
            await ClusterClient().set_defaults(defaults=state.defaults)
            selection_defaults_state = await state.get_state(SelectionDefaults)
            selection_defaults_state.defaults = state.defaults
            return [
                ClusterSettingsDialog.close
            ]

    @staticmethod
    @rx.event
    async def set_default_value(state: ClusterSettingsDialogState, setting: str, value: str) -> None:
        setattr(state.defaults, setting, value)

    @staticmethod
    @rx.event
    async def close(state: ClusterSettingsDialogState) -> rx.event.EventCallback:
        """Close the delete sector dialog and reset its state."""
        state.reset()
        return tailwind.Dialog.close(ClusterSettingsDialog.dialog_id)

    dialog_id: Final = "orbitlab-cluster-settings-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        storage_options = SelectOptions.node_storage_options.get(
            ClusterSettingsDialogState.defaults.node, default={},
        ).to(dict[StorageContentType, list[str]])
        return tailwind.Dialog(
            "Cluster Settings",
            tailwind.Tabs(
                tailwind.Tabs.Tab(
                    name="Defaults",
                    value="defaults",
                    content=tailwind.FieldSet(
                        "Defaults",
                        tailwind.FieldSet.Field(
                            "Proxmox Node: ",
                            tailwind.Select(
                                SelectOptions.node_options,
                                value=ClusterSettingsDialogState.defaults.node,
                                on_change=lambda value: cls.set_default_value("node", value),
                            ),
                            description="Primary Node",
                        ),
                        tailwind.FieldSet.Field(
                            "Vztmpl:",
                            tailwind.Select(
                                storage_options.get(StorageContentType.VZTMPL, default=[]).to(list[str]),
                                value=ClusterSettingsDialogState.defaults.vztmpl,
                                on_change=lambda value: cls.set_default_value("vztmpl", value),
                            ),
                            description="LXC Appliances",
                        ),
                        tailwind.FieldSet.Field(
                            "Imports:",
                            tailwind.Select(
                                storage_options.get(StorageContentType.IMPORT, default=[]).to(list[str]),
                                value=ClusterSettingsDialogState.defaults.imports,
                                on_change=lambda value: cls.set_default_value("imports", value),
                            ),
                            description="Importable Images",
                        ),
                        tailwind.FieldSet.Field(
                            "Rootdir:",
                            tailwind.Select(
                                storage_options.get(StorageContentType.ROOTDIR, default=[]).to(list[str]),
                                value=ClusterSettingsDialogState.defaults.rootdir,
                                on_change=lambda value: cls.set_default_value("rootdir", value),
                            ),
                            description="LXC Root Disks",
                        ),
                        tailwind.FieldSet.Field(
                            "Images:",
                            tailwind.Select(
                                storage_options.get(StorageContentType.IMAGES, default=[]).to(list[str]),
                                value=ClusterSettingsDialogState.defaults.images,
                                on_change=lambda value: cls.set_default_value("images", value),
                            ),
                            description="VM Disks",
                        ),
                    ),
                ),
                tailwind.Tabs.Tab(
                    name="Domain Providers",
                    value="domain-providers",
                    content=rx.fragment(
                        rx.el.div(
                            AddDomainProviderDialog(),
                            tailwind.Buttons.Primary(
                                "Add Domain Provider",
                                icon="plus",
                                on_click=AddDomainProviderDialog.open,
                            ),
                            class_name="w-full h-fit flex items-center justify-end",
                        ),
                        DomainProviderseTable(
                            name="Domain Providers",
                            headers=["Name", "Provider", "Email", ""],
                            data=OrbitLabState.domain_providers,
                            refresh=OrbitLabState.cache_clear("domain_providers"),
                        ),
                        UpdateDomainProviderCredentialDialog(),
                    )
                ),
                default_value="defaults",
                orientation="vertical",
            ),
            rx.el.div(
                rx.cond(
                    ClusterSettingsDialogState.initializing,
                    rx.fragment(),
                    tailwind.Buttons.Secondary("Close", on_click=cls.close),
                ),
                tailwind.Buttons.Primary("Save", on_click=cls.on_submit),
                class_name="w-full flex justify-end space-x-3",
            ),
            dialog_id=cls.dialog_id,
            class_name="min-w-[60vw] w-[60vw] min-h-[60vh] h-[60vh]",
        )
