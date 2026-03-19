"""DockFS Dialogs."""

from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.manifest.datacore import DataCoreManifest
from orbitlab.services import SecretVault
from orbitlab.web import components
from orbitlab.web.pages.sectors.dashboard.states import SectorsTableState
from orbitlab.web.utilities import EventGroup, get_worker

from .models import CreateDataCoreForm
from .states import CreateDataCoreDialogState, DataCoreServiceState, DeleteDataCoreDialogState


class CreateDataCoreDialog(EventGroup):
    """Dialog for creating DataCore clusters."""

    @staticmethod
    @rx.event
    async def submit(_: rx.State, form: dict) -> FrontendEvents:
        """Submit the DataCore creation form."""
        if "application_password" not in form:
            form["application_password"] = SecretVault.generate_random_password()
        manifest = DataCoreManifest.create(form_data=CreateDataCoreForm.model_validate(form))
        worker = get_worker()
        error = await worker.create_workflow(
            name="datacore.cluster.create",
            version="v1",
            payload={"manifest": manifest.name},
        )
        if error:
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Creating {manifest.name}..."),
            CreateDataCoreDialog.close,
        ]

    @staticmethod
    @rx.event
    async def toggle_view_password(state: CreateDataCoreDialogState) -> FrontendEvents:
        state.view_app_password = not state.view_app_password

    @staticmethod
    @rx.event
    async def close(state: CreateDataCoreDialogState) -> FrontendEvents:
        """Close the dialog."""
        state.reset()
        return components.Dialog.close(CreateDataCoreDialog.dialog_id)

    @staticmethod
    @rx.event
    async def open(_: rx.State) -> FrontendEvents:
        """Open the dialog."""
        return components.Dialog.open(CreateDataCoreDialog.dialog_id)

    dialog_id: Final = "create-datacore-cluster-dialog"
    form_id: Final = "create-datacore-cluster-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            "Create DataCore",
            rx.el.form(
                components.FieldSet(
                    "DataCore Configuration",
                    components.FieldSet.Field(
                        "Name: ",
                        components.Input(
                            placeholder="My App DataCore",
                            min="1",
                            max="128",
                            auto_complete="off",
                            form=cls.form_id,
                            name="name",
                            required=True,
                            error="Between 1 and 128 characters.",
                            class_name="w-full",
                        ),
                    ),
                    components.FieldSet.Field(
                        "Storage Capacity (Gb): ",
                        components.Slider(
                            default_value=CreateDataCoreDialogState.capacity_gb,
                            min=100,
                            max=2000,
                            step=50,
                            form=cls.form_id,
                            name="capacity_gb",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Number of Replicas: ",
                        components.Slider(
                            default_value=CreateDataCoreDialogState.replicas,
                            min=0,
                            max=5,
                            form=cls.form_id,
                            name="replicas",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Application Database: ",
                        components.Input(
                            placeholder="my-app-db",
                            min="1",
                            max="128",
                            auto_complete="datacore-db",
                            form=cls.form_id,
                            name="application_database",
                            required=True,
                            error="Between 1 and 128 characters.",
                            class_name="w-full",
                        ),
                    ),
                    components.FieldSet.Field(
                        "Application User: ",
                        components.Input(
                            placeholder="my-app-user",
                            min="1",
                            max="128",
                            auto_complete="datacore-db-user",
                            form=cls.form_id,
                            name="application_user",
                            required=True,
                            error="Between 1 and 128 characters.",
                            class_name="w-full",
                        ),
                    ),
                    components.FieldSet.Field(
                        "Application Password: ",
                        rx.el.div(
                            components.Input(
                                type=rx.cond(CreateDataCoreDialogState.view_app_password, "text", "password"),
                                placeholder="Leave blank for an auto-generated password",
                                min="12",
                                max="48",
                                auto_complete="datacore-db-password",
                                form=cls.form_id,
                                name="application_password",
                                error="Between 12 and 48 characters.",
                                class_name="w-full",
                            ),
                            components.Buttons.Icon(
                                rx.cond(CreateDataCoreDialogState.view_app_password, "eye-off", "eye"),
                                on_click=cls.toggle_view_password,
                                form="",
                            ),
                            class_name="w-full flex space-x-4",
                        )
                    ),
                ),
                components.FieldSet(
                    "Machine Configuration",
                    components.FieldSet.Field(
                        "Storage: ",
                        components.Select(
                            CreateDataCoreDialogState.available_rootdir_storages,
                            default_value=CreateDataCoreDialogState.rootdir_storage,
                            placeholder="Select Storage",
                            form=cls.form_id,
                            name="storage",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    components.FieldSet.Field(
                        "Cores: ",
                        components.Slider(
                            default_value=CreateDataCoreDialogState.cores,
                            min=1,
                            max=12,
                            form=cls.form_id,
                            name="cores",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Memory (GiB): ",
                        components.Slider(
                            default_value=CreateDataCoreDialogState.memory_gb,
                            min=1,
                            max=12,
                            form=cls.form_id,
                            name="memory_gb",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Sector",
                        components.Select(
                            SectorsTableState.sector_options,
                            form=cls.form_id,
                            name="sector",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.submit,
            ),
            rx.el.div(
                components.Buttons.Secondary("Close", on_click=CreateDataCoreDialog.close),
                components.Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex space-x-3 items-center justify-end",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-[50vw]",
        )


class DeleteDataCoreDialog(EventGroup):
    """Delete a DataCore cluster."""

    @staticmethod
    @rx.event
    async def confirm(state: DeleteDataCoreDialogState, name: str) -> FrontendEvents:
        """Set DataCore name to delete and open dialog."""
        state.reset()
        state.name = name
        return components.Dialog.open(DeleteDataCoreDialog.dialog_id)

    @staticmethod
    @rx.event
    async def update_confirmation(state: DeleteDataCoreDialogState, value: str) -> None:
        """Update the confirmation input text value."""
        state.confirmation = value

    @staticmethod
    @rx.event
    async def delete(state: DeleteDataCoreDialogState) -> FrontendEvents:
        """Delete the DataCore cluster."""
        worker = get_worker()
        error = await worker.create_workflow(
            name="datacore.cluster.delete",
            version="v1",
            payload={"manifest": state.name},
        )
        if error:
            return rx.toast.error(error)
        return [
            DeleteDataCoreDialog.close,
            rx.toast.info(f"Deleting {state.name}..."),
        ]

    @staticmethod
    @rx.event
    async def close(state: DeleteDataCoreDialogState) -> FrontendEvents:
        """Close the dialog."""
        state.reset()
        return components.Dialog.close(DeleteDataCoreDialog.dialog_id)

    dialog_id: Final = "confirm-delete-datacore-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return components.Dialog(
            f"Delete {DeleteDataCoreDialogState.name}",
            rx.el.div(
                rx.text(
                    "You are about to delete DataCore cluster '",
                    rx.el.span(DeleteDataCoreDialogState.name, class_name="font-bold"),
                    rx.el.span(
                        """'. This will delete all nodes and attached disks. This will not pevent
                        clients from attempting to connect to this DataCore after deletion.
                        """,
                    ),
                ),
                rx.text("If you are sure you want to delete this DataCore, type its name below."),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            components.Input(
                placeholder=DeleteDataCoreDialogState.name,
                on_change=cls.update_confirmation,
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.close),
                components.Buttons.Primary(
                    "Delete",
                    disabled=DeleteDataCoreDialogState.delete_disabled,
                    on_click=cls.delete,
                ),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )


class DeleteETCDDialog(EventGroup):
    """Delete the ETCD cluster."""

    @staticmethod
    @rx.event
    async def confirm(state: DataCoreServiceState) -> FrontendEvents:
        """Open the dialog."""
        if len(state.clusters) > 0:
            return rx.toast.error("You must remove all existing DataCores before deleting ETCD.")
        return components.Dialog.open(DeleteETCDDialog.dialog_id)

    @staticmethod
    @rx.event
    async def update_confirmation(state: DataCoreServiceState, value: str) -> None:
        """Update the confirmation input text value."""
        state.confirm_delete_etcd = value

    @staticmethod
    @rx.event
    async def delete(state: DataCoreServiceState) -> FrontendEvents:
        """Delete the DataCore cluster."""
        worker = get_worker()
        error = await worker.create_workflow(
            name="datacore.etcd.delete",
            version="v1",
            payload={},
        )
        if error:
            return rx.toast.error(error)
        return [
            DeleteETCDDialog.close,
            rx.toast.info(f"Deleting ETCD..."),
        ]

    @staticmethod
    @rx.event
    async def close(state: DataCoreServiceState) -> FrontendEvents:
        """Close the dialog."""
        state.confirm_delete_etcd = ""
        return components.Dialog.close(DeleteETCDDialog.dialog_id)

    dialog_id: Final = "confirm-delete-etcd-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return components.Dialog(
            f"Delete ETCD",
            rx.el.div(
                rx.text(
                    (
                        "You are about to delete the ETCD cluster. You will not be able to create any new "
                        "DataCores until the ETCD cluster is re-created."
                    )
                ),
                rx.text(
                    "If you are sure you want to delete the ETCD cluster, type ",
                    rx.el.span("delete", class_name="font-bold"),
                    " in the box below."
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            components.Input(
                placeholder="delete",
                auto_complete="off",
                on_change=cls.update_confirmation,
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.close),
                components.Buttons.Primary(
                    "Delete",
                    disabled=DataCoreServiceState.confirm_delete_etcd != "delete",
                    on_click=cls.delete,
                ),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )
