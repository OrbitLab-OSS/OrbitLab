"""DockFS Dialogs."""

from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents, StorageContentType
from orbitlab.redis.clients import DockFSClient, SectorClient
from orbitlab.redis.models import DockFSConfig
from orbitlab.web import tailwind
from orbitlab.web.global_state import SelectOptions, SelectionDefaults
from orbitlab.web.utilities import EventGroup, create_workflow

from .states import DeleteDockFSDialogState


class CreateDockFSDialog(EventGroup):
    """Dialog for creating DockFS clusters."""

    @staticmethod
    @rx.event
    async def submit(_: rx.State, form: dict) -> FrontendEvents:
        """Submit the DockFS creation form."""
        client = DockFSClient()
        sector = SectorClient()
        sector_vip = await sector.acquire_vip(id=form["sector"])

        form["id"] = await client.generate_cluster_id()
        form["sector_name"] = (await sector.get(id=form["sector"])).config.alias
        form["virtual_router_id"] = sector_vip.virtual_router_id
        form["vip"] = sector_vip.address
        
        config = DockFSConfig.model_validate(form)
        await client.set_dockfs(config=config)
        
        if error := await create_workflow(name="dockfs.create", version="v1", payload={"id": config.id}):
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Creating {config.id}..."),
            tailwind.Dialog.close(CreateDockFSDialog.dialog_id),
        ]

    dialog_id: Final = "create-dockfs-cluster-dialog"
    form_id: Final = "create-dockfs-cluster-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        storage_options = SelectOptions.node_storage_options.get(
            SelectionDefaults.default_node, default={},
        ).to(dict).get(StorageContentType.IMAGES, []).to(list[str])
        return tailwind.Dialog(
            "Create DockFS",
            rx.el.form(
                tailwind.FieldSet(
                    "DockFS Configuration",
                    tailwind.FieldSet.Field(
                        "Name: ",
                        tailwind.Input(
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
                        "Sector",
                        tailwind.Select(
                            SelectOptions.sector_options,
                            name="sector",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                ),
                tailwind.FieldSet(
                    "Machine Configuration",
                    tailwind.FieldSet.Field(
                        "Storage: ",
                        tailwind.Select(
                            storage_options,
                            default_value=SelectionDefaults.default_images_storage,
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
                        "Sockets: ",
                        tailwind.Slider(
                            default_value=1,
                            min=1,
                            max=2,
                            form=cls.form_id,
                            name="sockets",
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
                            name="memory",
                            required=True,
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.submit,
            ),
            rx.el.div(
                tailwind.Buttons.Secondary("Close", on_click=tailwind.Dialog.close(CreateDockFSDialog.dialog_id)),
                tailwind.Buttons.Primary("Submit", form=cls.form_id),
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
        return tailwind.Dialog.open(DeleteDockFSDialog.dialog_id)

    @staticmethod
    @rx.event
    async def update_confirmation(state: DeleteDockFSDialogState, value: str) -> None:
        """Update the confirmation input text value."""
        state.confirmation = value

    @staticmethod
    @rx.event
    async def delete(state: DeleteDockFSDialogState) -> FrontendEvents:
        """Delete a custom appliance from Proxmox and remove its manifest."""
        if error := await create_workflow(name="dockfs.delete", version="v1", payload={"id": state.name}):
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
        return tailwind.Dialog.close(DeleteDockFSDialog.dialog_id)

    dialog_id: Final = "confirm-delete-dockfs-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return tailwind.Dialog(
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
            tailwind.Input(
                placeholder=DeleteDockFSDialogState.name,
                on_change=cls.update_confirmation,
            ),
            rx.el.div(
                tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                tailwind.Buttons.Primary(
                    "Delete",
                    disabled=DeleteDockFSDialogState.delete_disabled,
                    on_click=cls.delete,
                ),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )
