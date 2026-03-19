"""DockFS Dialogs."""

from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.manifest.dockfs import DockFsManifest
from orbitlab.web import components
from orbitlab.web.utilities import EventGroup, get_worker

from .models import CreateDockFSform
from .states import CreateDockFSDialogState, DeleteDockFSDialogState


class CreateDockFSDialog(EventGroup):
    """Dialog for creating DockFS clusters."""

    @staticmethod
    @rx.event
    async def submit(_: rx.State, form: dict) -> FrontendEvents:
        """Submit the DockFS creation form."""
        manifest = DockFsManifest.create(form_data=CreateDockFSform.model_validate(form))
        worker = get_worker()
        error = await worker.create_workflow(
            name="dockfs.create",
            version="v1",
            payload={"manifest": manifest.name},
        )
        if error:
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Creating {manifest.name}..."),
            CreateDockFSDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: CreateDockFSDialogState) -> FrontendEvents:
        """Close the dialog."""
        state.reset()
        return components.Dialog.close(CreateDockFSDialog.dialog_id)

    @staticmethod
    @rx.event
    async def open(_: rx.State) -> FrontendEvents:
        """Open the dialog."""
        return components.Dialog.open(CreateDockFSDialog.dialog_id)

    dialog_id: Final = "create-dockfs-cluster-dialog"
    form_id: Final = "create-dockfs-cluster-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            "Create DockFS",
            rx.el.form(
                components.FieldSet(
                    "DockFS Configuration",
                    components.FieldSet.Field(
                        "Name: ",
                        components.Input(
                            placeholder="My Media",
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
                        "Disk Store: ",
                        components.Select(
                            CreateDockFSDialogState.available_disk_storages,
                            default_value=CreateDockFSDialogState.disk_storage,
                            placeholder="Select Storage",
                            form=cls.form_id,
                            name="storage",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    components.FieldSet.Field(
                        "Storage Capacity (Gb): ",
                        components.Slider(
                            default_value=CreateDockFSDialogState.capacity_gb,
                            min=100,
                            max=2000,
                            step=50,
                            form=cls.form_id,
                            name="capacity_gb",
                            required=True,
                        ),
                    ),
                ),
                components.FieldSet(
                    "Machine Configuration",
                    components.FieldSet.Field(
                        "Cores: ",
                        components.Slider(
                            default_value=CreateDockFSDialogState.cores,
                            min=1,
                            max=12,
                            form=cls.form_id,
                            name="cores",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Sockets: ",
                        components.Slider(
                            default_value=CreateDockFSDialogState.sockets,
                            min=1,
                            max=2,
                            form=cls.form_id,
                            name="sockets",
                            required=True,
                        ),
                    ),
                    components.FieldSet.Field(
                        "Memory (GiB): ",
                        components.Slider(
                            default_value=CreateDockFSDialogState.memory_gb,
                            min=1,
                            max=12,
                            form=cls.form_id,
                            name="memory",
                            required=True,
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.submit,
            ),
            rx.el.div(
                components.Buttons.Secondary("Close", on_click=CreateDockFSDialog.close),
                components.Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex space-x-3 items-center justify-end",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-[50vw]",
        )


class DeleteDockFSDialog(EventGroup):
    """Delete a DockFS cluster."""

    @staticmethod
    @rx.event
    async def confirm(state: DeleteDockFSDialogState, name: str) -> FrontendEvents:
        """Set DockFS name to delete and open dialog."""
        state.reset()
        state.name = name
        return components.Dialog.open(DeleteDockFSDialog.dialog_id)

    @staticmethod
    @rx.event
    async def update_confirmation(state: DeleteDockFSDialogState, value: str) -> None:
        """Update the confirmation input text value."""
        state.confirmation = value

    @staticmethod
    @rx.event
    async def delete(state: DeleteDockFSDialogState) -> FrontendEvents:
        """Delete a custom appliance from Proxmox and remove its manifest."""
        worker = get_worker()
        error = await worker.create_workflow(
            name="dockfs.delete",
            version="v1",
            payload={"manifest": state.name},
        )
        if error:
            return rx.toast.error(error)
        return [
            DeleteDockFSDialog.close,
            rx.toast.info(f"Deleting {state.name}..."),
        ]

    @staticmethod
    @rx.event
    async def close(state: DeleteDockFSDialogState) -> FrontendEvents:
        """Cancel custom appliance deletion and close the dialog."""
        state.reset()
        return components.Dialog.close(DeleteDockFSDialog.dialog_id)

    dialog_id: Final = "confirm-delete-dockfs-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return components.Dialog(
            f"Delete {DeleteDockFSDialogState.name}",
            rx.el.div(
                rx.text(
                    "You are about to delete DockFS cluster '",
                    rx.el.span(DeleteDockFSDialogState.name, class_name="font-bold"),
                    rx.el.span(
                        """'. This will delete all nodes and attached disks. This will not pevent
                        clients from attempting to connect to this DockFS after deletion.
                        """,
                    ),
                ),
                rx.text("If you are sure you want to delete this DockFS, type its name below."),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            components.Input(
                placeholder=DeleteDockFSDialogState.name,
                on_change=cls.update_confirmation,
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.close),
                components.Buttons.Primary(
                    "Delete",
                    disabled=DeleteDockFSDialogState.delete_disabled,
                    on_click=cls.delete,
                ),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )
