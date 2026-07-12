from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.web import tailwind
from orbitlab.web.global_state import SelectOptions, SelectionDefaults
from orbitlab.web.utilities import EventGroup

from .states import CreatePoolDialogState


class CreatePoolDialog(EventGroup):

    @staticmethod
    @rx.event
    async def open(state: CreatePoolDialogState) -> FrontendEvents:
        """Initialize appliance creation from a base appliance and open the dialog."""
        state.form_data["node"] = await state.get_var_value(SelectionDefaults.default_node)
        state.form_data["storage"] = await state.get_var_value(SelectionDefaults.default_vztmpl_storage)
        state.form_data["rootfs"] = await state.get_var_value(SelectionDefaults.default_rootdir_storage)
        return tailwind.Dialog.open(CreatePoolDialog.dialog_id)

    @staticmethod
    @rx.event
    async def set_node(state: CreatePoolDialogState, node: str) -> None:
        """Set the selected node and clear storage selection."""
        state.form_data["node"] = node
        if "storage" in state.form_data:
            del state.form_data["storage"]

    @staticmethod
    @rx.event
    async def create_pool(state: CreatePoolDialogState, form: dict) -> FrontendEvents:
        """Create the custom appliance with the configured settings and workflow steps."""
        print(form)
        

    @staticmethod
    @rx.event
    async def close(state: CreatePoolDialogState) -> FrontendEvents:
        state.reset()
        return [
            tailwind.Dialog.close(CreatePoolDialog.dialog_id),
        ]

    dialog_id: Final = "create-autoscaling-pool-dialog"
    form_id: Final = "create-autoscaling-pool-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
            "Create Autoscaling Pool",
            rx.el.form(
                tailwind.FieldSet(
                    "Pool Configuration",
                    tailwind.FieldSet.Field(
                        "Pool Name: ",
                        tailwind.Input(
                            placeholder="My Pool",
                            min="1",
                            max="128",
                            name="name",
                            required=True,
                            auto_complete="off",
                            class_name="w-full",
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
                    tailwind.FieldSet.Field(
                        "Compute Type: ",
                        rx.el.div(
                            tailwind.Buttons.Secondary(
                                "LXC",
                                on_click=CreatePoolDialogState.toggle_compute_type,
                                disabled=CreatePoolDialogState.compute_type == "lxc",
                                form=""
                            ),
                            tailwind.Buttons.Secondary(
                                "VM",
                                on_click=CreatePoolDialogState.toggle_compute_type,
                                disabled=CreatePoolDialogState.compute_type == "vm",
                                form=""
                            ),
                            class_name="w-full flex space-x-4 justify-start items-center"
                        )
                    ),
                    tailwind.FieldSet.Field(
                        "Base: ",
                        tailwind.Select(
                            CreatePoolDialogState.available_bases,
                            placeholder="Select Base",
                            name="base",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Root Password",
                        rx.el.div(
                            tailwind.Input(
                                type="password",
                                error="Must be between 8 to 64 characters",
                                min="8",
                                max="64",
                                name="password",
                                class_name="w-full",
                            ),
                            rx.text(
                                "If not provided, the password will be randomly generated.",
                                class_name="text-sm font-light opacity-50",
                            ),
                            class_name="w-full flex-col space-y-1 justify-start align-start",
                        ),
                    ),
                ),
                tailwind.FieldSet(
                    "Compute Configuration",
                    tailwind.FieldSet.Field(
                        "Node: ",
                        tailwind.Select(
                            SelectOptions.node_options,
                            placeholder="Select Node",
                            default_value=SelectionDefaults.default_node,
                            on_change=cls.set_node,
                            name="node",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Disk Storage: ",
                        tailwind.Select(
                            CreatePoolDialogState.available_storage,
                            default_value=rx.cond(
                                CreatePoolDialogState.compute_type == "lxc",
                                SelectionDefaults.default_rootdir_storage,
                                SelectionDefaults.default_images_storage,
                            ),
                            placeholder="Select Storage",
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
                            max=8,
                            name="cores",
                            required=True,
                        ),
                    ),
                    rx.cond(
                        CreatePoolDialogState.compute_type == "vm",
                        tailwind.FieldSet.Field(
                            "Sockets: ",
                            tailwind.Slider(
                                default_value=1,
                                min=1,
                                max=2,
                                name="sockets",
                                required=True,
                            ),
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Memory (GiB): ",
                        tailwind.Slider(
                            default_value=2,
                            min=1,
                            max=12,
                            name="memory",
                            required=True,
                        ),
                    ),
                    rx.cond(
                        CreatePoolDialogState.compute_type == "lxc",
                        tailwind.FieldSet.Field(
                            "Swap (MiB): ",
                            tailwind.Slider(
                                default_value=256,
                                min=256,
                                max=2048,
                                step=256,
                                name="swap",
                                required=True,
                            ),
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.create_pool
            ),
            rx.el.div(
                tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                tailwind.Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex justify-end space-x-4 mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )
