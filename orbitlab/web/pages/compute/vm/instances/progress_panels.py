"""OrbitLab Launch LXC Progress Panels."""

import reflex as rx

from orbitlab.web import components
from orbitlab.web.pages.nodes.states import ProxmoxState
from orbitlab.web.utilities import EventGroup

from .states import LaunchVMDialogState


class GeneralConfigurationPanel(EventGroup):
    """Panel for configuring general appliance settings."""

    @staticmethod
    @rx.event
    async def set_node(state: LaunchVMDialogState, node: str) -> None:
        """Set the selected node and clear storage selection."""
        state.form_data["node"] = node
        if "storage" in state.form_data:
            del state.form_data["storage"]

    @staticmethod
    @rx.event
    async def set_storage(state: LaunchVMDialogState, storage: str) -> None:
        """Set the storage selection in the form data."""
        state.form_data["storage"] = storage


    @staticmethod
    @rx.event
    async def set_sector(state: LaunchVMDialogState, sector: str) -> None:
        """Set the network name for a specific network configuration."""
        state.sector = sector

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        return rx.fragment(
            components.FieldSet(
                "Proxmox",
                components.FieldSet.Field(
                    "Image: ",
                    components.Select(
                        LaunchVMDialogState.available_images,
                        default_value=LaunchVMDialogState.image,
                        placeholder="Select Image",
                        name="image",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                components.FieldSet.Field(
                    "Hostname: ",
                    components.Input(
                        placeholder="my-vm",
                        default_value=LaunchVMDialogState.name,
                        error="Names can be up to 64 alphanumeric characters, hyphens, and underscores.",
                        min="1",
                        max="64",
                        name="name",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                components.FieldSet.Field(
                    "Node: ",
                    components.Select(
                        ProxmoxState.node_names,
                        placeholder="Select Node",
                        default_value=LaunchVMDialogState.node,
                        on_change=cls.set_node,
                        name="node",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                components.FieldSet.Field(
                    "Disk Store: ",
                    components.Select(
                        LaunchVMDialogState.available_disk_storages,
                        default_value=LaunchVMDialogState.disk_storage,
                        on_change=cls.set_storage,
                        placeholder="Select Storage",
                        name="storage",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                components.FieldSet.Field(
                    "Disk Size (Gb): ",
                    components.Slider(
                        default_value=LaunchVMDialogState.disk_size_gb,
                        min=8,
                        max=2000,
                        name="disk_size",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Cores: ",
                    components.Slider(
                        default_value=LaunchVMDialogState.cores,
                        min=1,
                        max=12,
                        name="cores",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Sockets: ",
                    components.Slider(
                        default_value=LaunchVMDialogState.sockets,
                        min=1,
                        max=2,
                        name="sockets",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Memory (GiB): ",
                    components.Slider(
                        default_value=LaunchVMDialogState.memory_gb,
                        min=1,
                        max=12,
                        name="memory",
                        required=True,
                    ),
                ),
            ),
            components.FieldSet(
                "Networking",
                components.FieldSet.Field(
                    "Sector",
                    components.Select(
                        LaunchVMDialogState.sectors,
                        value=LaunchVMDialogState.sector,
                        on_change=cls.set_sector,
                        name="sector",
                        required=True,
                        class_name="w-full",
                    ),
                ),
            ),
            components.FieldSet(
                "Secrets",
                components.FieldSet.Field(
                    "Root Password",
                    rx.el.div(
                        components.Input(
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
                components.FieldSet.Field(
                    "SSH Key",
                    rx.text("Not currently supported", class_name="font-light italic"),
                ),
            ),
        )


class ReviewPanel:
    """Panel for reviewing appliance configuration before creation."""

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        return rx.fragment(
            components.DataList(
                components.DataList.Item(
                    components.DataList.Label("Hostname"),
                    components.DataList.Value(LaunchVMDialogState.name),
                ),
                components.DataList.Item(
                    components.DataList.Label("Image"),
                    components.DataList.Value(LaunchVMDialogState.image),
                ),
                components.DataList.Item(
                    components.DataList.Label("Disk Store"),
                    components.DataList.Value(LaunchVMDialogState.disk_storage),
                ),
                components.DataList.Item(
                    components.DataList.Label("Disk Size"),
                    components.DataList.Value(f"{LaunchVMDialogState.disk_size_gb}GB"),
                ),
                components.DataList.Item(
                    components.DataList.Label("Memory"),
                    components.DataList.Value(f"{LaunchVMDialogState.memory_gb}GiB"),
                ),
                components.DataList.Item(
                    components.DataList.Label("vCPUs"),
                    components.DataList.Value(
                        f"{LaunchVMDialogState.cores * LaunchVMDialogState.sockets} "
                        f"({LaunchVMDialogState.cores} cores, {LaunchVMDialogState.sockets} socket)",
                    ),
                ),
                components.DataList.Item(
                    components.DataList.Label("Network"),
                    components.DataList.Value(LaunchVMDialogState.sector),
                ),
            ),
        )
