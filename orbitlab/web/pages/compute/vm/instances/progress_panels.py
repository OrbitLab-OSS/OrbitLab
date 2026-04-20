"""OrbitLab Launch LXC Progress Panels."""

import reflex as rx

from orbitlab.data_types import StorageContentType
from orbitlab.web import tailwind
from orbitlab.web.global_state import SelectOptions, SelectionDefaults
from orbitlab.web.utilities import EventGroup

from .states import LaunchVMDialogState


class GeneralConfigurationPanel(EventGroup):
    """Panel for configuring general appliance settings."""

    @staticmethod
    @rx.event
    async def set_node(state: LaunchVMDialogState, node: str) -> None:
        """Set the selected node and clear storage selection."""
        state.form_data["node"] = node
        return rx.set_value("vm-instance-disk-storage", "")

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        selected_node = LaunchVMDialogState.form_data.get("node", default=SelectionDefaults.default_node).to(str)
        storage_options = SelectOptions.node_storage_options.get(
            selected_node, default={},
        ).to(dict).get(StorageContentType.IMAGES, default=[]).to(list[str])
        return rx.fragment(
            tailwind.FieldSet(
                "Instance Configuration",
                tailwind.FieldSet.Field(
                    "Hostname: ",
                    tailwind.Input(
                        placeholder="my-vm",
                        auto_complete="off",
                        error="Names can be up to 64 alphanumeric characters, hyphens, and underscores.",
                        min="1",
                        max="64",
                        name="name",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                tailwind.FieldSet.Field(
                    "Image: ",
                    tailwind.Select(
                        SelectOptions.all_image_options,
                        placeholder="Select Image",
                        name="image",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                tailwind.FieldSet.Field(
                    "Disk Size (Gb): ",
                    tailwind.Slider(
                        default_value=10,
                        min=8,
                        max=2000,
                        name="disk_size",
                        required=True,
                    ),
                ),
                tailwind.FieldSet.Field(
                    "Cores: ",
                    tailwind.Slider(
                        default_value=2,
                        min=1,
                        max=12,
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
                        name="memory",
                        required=True,
                    ),
                ),
            ),
            tailwind.FieldSet(
                "Proxmox Configuration",
                tailwind.FieldSet.Field(
                    "Node: ",
                    tailwind.Select(
                        SelectOptions.node_options,
                        placeholder="Select Node",
                        default_value=selected_node,
                        on_change=cls.set_node,
                        name="node",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                tailwind.FieldSet.Field(
                    "Disk Store: ",
                    tailwind.Select(
                        storage_options,
                        default_value=SelectionDefaults.default_images_storage,
                        placeholder="Select Storage",
                        name="storage",
                        required=True,
                        class_name="w-full",
                        id="vm-instance-disk-storage"
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
                "Secrets",
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
                        class_name="flex-col space-y-1 justify-start align-start",
                    ),
                ),
                tailwind.FieldSet.Field(
                    "SSH Key",
                    rx.text("Not currently supported", class_name="font-light italic"),
                ),
            ),
        )


class ReviewPanel:
    """Panel for reviewing appliance configuration before creation."""

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        cores = LaunchVMDialogState.form_data.get("cores", default=0).to(int)
        sockets = LaunchVMDialogState.form_data.get("sockets", default=0).to(int)
        vcpus = (cores * sockets).to(int)
        memory = LaunchVMDialogState.form_data.get("memory")
        disk_size = LaunchVMDialogState.form_data.get("disk_size")
        return rx.fragment(
            tailwind.DataList(
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Hostname"),
                    tailwind.DataList.Value(LaunchVMDialogState.form_data.get("name")),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Image"),
                    tailwind.DataList.Value(LaunchVMDialogState.form_data.get("image")),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Disk Store"),
                    tailwind.DataList.Value(LaunchVMDialogState.form_data.get("storage")),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Disk Size"),
                    tailwind.DataList.Value(f"{disk_size} GB"),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Memory"),
                    tailwind.DataList.Value(f"{memory} GiB"),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("vCPUs"),
                    tailwind.DataList.Value(f"{vcpus} ({cores} cores, {sockets} sockets)"),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Sector"),
                    tailwind.DataList.Value(LaunchVMDialogState.form_data.get("sector")),
                ),
            ),
        )
