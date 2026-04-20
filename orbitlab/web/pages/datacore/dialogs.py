"""DockFS Dialogs."""

from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents, StorageContentType
from orbitlab.redis.clients import DataCoreClient, SecretsClient, SectorClient
from orbitlab.redis.models import DataCoreConfig
from orbitlab.web import tailwind
from orbitlab.web.global_state import ETCDState, InfrastructureManagementState, OrbitLabState, SelectOptions, SelectionDefaults
from orbitlab.web.utilities import EventGroup, create_workflow

from .states import CreateDataCoreDialogState, DataCoreServiceState, DeleteDataCoreDialogState


class CreateDataCoreDialog(EventGroup):
    """Dialog for creating DataCore clusters."""

    @staticmethod
    @rx.event
    async def submit(_: rx.State, form: dict) -> FrontendEvents:
        """Submit the DataCore creation form."""
        if "application_password" not in form:
            form["application_password"] = SecretsClient.generate_random_password()
        datacore_id = await DataCoreClient().generate_cluster_id()
        await SecretsClient().create_service_secret(
            service_name="datacore",
            service_id=datacore_id,
            subservice_name=form["application_user"],
            value=form.get("application_password", "")
        )
        await SecretsClient().create_service_secret(
            service_name="datacore",
            service_id=datacore_id,
            subservice_name="superuser",
        )
        await SecretsClient().create_service_secret(
            service_name="datacore",
            service_id=datacore_id,
            subservice_name="replication",
        )
        rw_vip = await SectorClient().acquire_vip(id=form["sector"])
        ro_vip = await SectorClient().acquire_vip(id=form["sector"])
        datacore = await DataCoreClient().set_datacore(
            config=DataCoreConfig(
                id=DataCoreClient().generate_cluster_id(),
                name=form["name"],
                rw_virtual_router_id=rw_vip.virtual_router_id,
                rw_vip=rw_vip.address,
                ro_virtual_router_id=ro_vip.virtual_router_id,
                ro_vip=ro_vip.address,
                replicas=int(form["replicas"]),
                memory_gb=int(form["memory_gb"]),
                cores=int(form["cores"]),
                capacity_gb=int(form["capacity_gb"]),
                storage=form["storage"],
                sector=form["sector"],
                application_user=form["application_user"],
                application_database=form["application_database"],
            )
        )
        if error := await create_workflow(name="datacore.cluster.create", version="v1", payload={"id": datacore.config.id}):
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Creating {datacore.config.name}..."),
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
        return tailwind.Dialog.close(CreateDataCoreDialog.dialog_id)

    @staticmethod
    @rx.event
    async def open(_: rx.State) -> FrontendEvents:
        """Open the dialog."""
        return tailwind.Dialog.open(CreateDataCoreDialog.dialog_id)

    dialog_id: Final = "create-datacore-cluster-dialog"
    form_id: Final = "create-datacore-cluster-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        storage_options = SelectOptions.node_storage_options.get(
            SelectionDefaults.default_node, default={},
        ).to(dict).get(StorageContentType.ROOTDIR, []).to(list[str])
        return tailwind.Dialog(
            "Create DataCore",
            rx.el.form(
                tailwind.FieldSet(
                    "DataCore Configuration",
                    tailwind.FieldSet.Field(
                        "Name: ",
                        tailwind.Input(
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
                    tailwind.FieldSet.Field(
                        "Storage Capacity (Gb): ",
                        tailwind.Slider(
                            default_value=100,
                            min=100,
                            max=2000,
                            step=50,
                            form=cls.form_id,
                            name="capacity_gb",
                            required=True,
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Number of Replicas: ",
                        tailwind.Slider(
                            default_value=1,
                            min=0,
                            max=5,
                            form=cls.form_id,
                            name="replicas",
                            required=True,
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Application Database: ",
                        tailwind.Input(
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
                    tailwind.FieldSet.Field(
                        "Application User: ",
                        tailwind.Input(
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
                    tailwind.FieldSet.Field(
                        "Application Password: ",
                        rx.el.div(
                            tailwind.Input(
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
                            tailwind.Buttons.Icon(
                                rx.cond(CreateDataCoreDialogState.view_app_password, "eye-off", "eye"),
                                on_click=cls.toggle_view_password,
                                form="",
                            ),
                            class_name="w-full flex space-x-4",
                        )
                    ),
                ),
                tailwind.FieldSet(
                    "Machine Configuration",
                    tailwind.FieldSet.Field(
                        "Storage: ",
                        tailwind.Select(
                            storage_options,
                            default_value=SelectionDefaults.default_rootdir_storage,
                            placeholder="Select Storage",
                            form=cls.form_id,
                            name="storage",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Cores: ",
                        tailwind.Slider(
                            default_value=2,
                            min=1,
                            max=12,
                            form=cls.form_id,
                            name="cores",
                            required=True,
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Memory (GiB): ",
                        tailwind.Slider(
                            default_value=2,
                            min=1,
                            max=12,
                            form=cls.form_id,
                            name="memory_gb",
                            required=True,
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Sector",
                        tailwind.Select(
                            SelectOptions.sector_options,
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
                tailwind.Buttons.Secondary("Close", on_click=CreateDataCoreDialog.close),
                tailwind.Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex space-x-3 items-center justify-end",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-[50vw]",
        )


class DeleteDataCoreDialog(EventGroup):
    """Delete a DataCore cluster."""

    @staticmethod
    @rx.event
    async def confirm(state: DeleteDataCoreDialogState, datacore_id: str) -> FrontendEvents:
        """Set DataCore name to delete and open dialog."""
        state.reset()
        state.datacore_id = datacore_id
        return tailwind.Dialog.open(DeleteDataCoreDialog.dialog_id)

    @staticmethod
    @rx.event
    async def update_confirmation(state: DeleteDataCoreDialogState, value: str) -> None:
        """Update the confirmation input text value."""
        state.confirmation = value

    @staticmethod
    @rx.event
    async def delete(state: DeleteDataCoreDialogState) -> FrontendEvents:
        """Delete the DataCore cluster."""
        if error := await create_workflow(name="datacore.cluster.delete", version="v1", payload={"id": state.datacore_id}):
            return rx.toast.error(error)
        return [
            DeleteDataCoreDialog.close,
            rx.toast.info(f"Deleting {state.datacore_id}..."),
        ]

    @staticmethod
    @rx.event
    async def close(state: DeleteDataCoreDialogState) -> FrontendEvents:
        """Close the dialog."""
        state.reset()
        return tailwind.Dialog.close(DeleteDataCoreDialog.dialog_id)

    dialog_id: Final = "confirm-delete-datacore-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return tailwind.Dialog(
            f"Delete {DeleteDataCoreDialogState.datacore_id}",
            rx.el.div(
                rx.text(
                    "You are about to delete DataCore cluster '",
                    rx.el.span(DeleteDataCoreDialogState.datacore_id, class_name="font-bold"),
                    rx.el.span(
                        """'. This will delete all nodes and attached disks. This will not pevent
                        clients from attempting to connect to this DataCore after deletion.
                        """,
                    ),
                ),
                rx.text("If you are sure you want to delete this DataCore, type its name below."),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            tailwind.Input(
                placeholder=DeleteDataCoreDialogState.datacore_id,
                on_change=cls.update_confirmation,
            ),
            rx.el.div(
                tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                tailwind.Buttons.Primary(
                    "Delete",
                    disabled=DeleteDataCoreDialogState.delete_disabled,
                    on_click=cls.delete,
                ),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )


class UpgradeETCDDialog(EventGroup):
    """Upgrade the ETCD cluster."""

    @staticmethod
    @rx.event
    async def upgrade(_: rx.State) -> FrontendEvents:
        """Delete the DataCore cluster."""
        if error := await create_workflow(name="datacore.etcd.upgrade", version="v1", payload={}):
            return rx.toast.error(error)
        return [
            tailwind.Dialog.close(UpgradeETCDDialog.dialog_id),
            rx.toast.info("Upgading ETCD cluster..."),
        ]

    dialog_id: Final = "confirm-upgrade-etcd-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return tailwind.Dialog(
            "Upgrade ETCD",
            rx.el.div(
                rx.text(
                    (
                        "You are about to upgrade the ETCD cluster from "
                        f"v{ETCDState.version} to v{InfrastructureManagementState.latest_version}. "
                        "This process will upgrade one member node at a time by creating a replacement node with the new "
                        "appliance version and then removing its predecessor."
                    )
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            rx.el.div(
                tailwind.Buttons.Secondary("Cancel", on_click=tailwind.Dialog.close(UpgradeETCDDialog.dialog_id)),
                tailwind.Buttons.Primary("Begin", on_click=cls.upgrade),
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
        if len(await state.get_var_value(OrbitLabState.datacores)) > 0:
            return rx.toast.error("You must remove all existing DataCores before deleting ETCD.")
        return tailwind.Dialog.open(DeleteETCDDialog.dialog_id)

    @staticmethod
    @rx.event
    async def update_confirmation(state: DataCoreServiceState, value: str) -> None:
        """Update the confirmation input text value."""
        state.confirm_delete_etcd = value

    @staticmethod
    @rx.event
    async def delete(state: DataCoreServiceState) -> FrontendEvents:
        """Delete the DataCore cluster."""
        if error := await create_workflow(name="datacore.etcd.delete", version="v1", payload={}):
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
        return tailwind.Dialog.close(DeleteETCDDialog.dialog_id)

    dialog_id: Final = "confirm-delete-etcd-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return tailwind.Dialog(
            "Delete ETCD",
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
            tailwind.Input(
                placeholder="delete",
                auto_complete="off",
                on_change=cls.update_confirmation,
            ),
            rx.el.div(
                tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                tailwind.Buttons.Primary(
                    "Delete",
                    disabled=DataCoreServiceState.confirm_delete_etcd != "delete",
                    on_click=cls.delete,
                ),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )
