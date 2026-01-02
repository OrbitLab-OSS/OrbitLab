"""OrbitLab Launch LXC Progress Panels."""

import reflex as rx

from orbitlab.web import components
from orbitlab.web.pages.nodes.states import ProxmoxState
from orbitlab.web.utilities import EventGroup

from .states import LaunchLXCState


class GeneralConfigurationPanel(EventGroup):
    """Panel for configuring general appliance settings."""

    @staticmethod
    @rx.event
    async def set_node(state: LaunchLXCState, node: str) -> None:
        """Set the selected node and clear storage selection."""
        state.form_data["node"] = node
        if "storage" in state.form_data:
            del state.form_data["storage"]

    @staticmethod
    @rx.event
    async def set_storage(state: LaunchLXCState, storage: str) -> None:
        """Set the storage selection in the form data."""
        state.form_data["storage"] = storage

    @staticmethod
    @rx.event
    async def set_rootdir(state: LaunchLXCState, storage: str) -> None:
        """Set the storage selection in the form data."""
        state.form_data["rootdir"] = storage

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        return rx.fragment(
            components.FieldSet(
                "Proxmox",
                components.FieldSet.Field(
                    "Appliance: ",
                    components.Select(
                        LaunchLXCState.appliances,
                        default_value=LaunchLXCState.appliance,
                        placeholder="Select Appliance",
                        name="appliance",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Hostname: ",
                    components.Input(
                        placeholder="my-lxc",
                        default_value=LaunchLXCState.name,
                        error="Names can be up to 64 alphanumeric characters, hyphens, and underscores.",
                        min="1",
                        max="64",
                        name="name",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Node: ",
                    components.Select(
                        ProxmoxState.node_names,
                        placeholder="Select Node",
                        default_value=LaunchLXCState.node,
                        on_change=cls.set_node,
                        name="node",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Disk Store: ",
                    components.Select(
                        LaunchLXCState.available_rootfs,
                        default_value=LaunchLXCState.rootfs,
                        on_change=cls.set_rootdir,
                        placeholder="Select Storage",
                        name="rootfs",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Disk Size (Gb): ",
                    components.Slider(
                        default_value=LaunchLXCState.disk_size_gb,
                        min=8,
                        max=128,
                        name="disk_size",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Cores: ",
                    components.Slider(
                        default_value=LaunchLXCState.cores,
                        min=1,
                        max=8,
                        name="cores",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Memory (GiB): ",
                    components.Slider(
                        default_value=LaunchLXCState.memory_gb,
                        min=1,
                        max=12,
                        name="memory",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Swap (GiB): ",
                    components.Slider(
                        default_value=LaunchLXCState.swap_gb,
                        min=1,
                        max=12,
                        name="swap",
                        required=True,
                    ),
                ),
            ),
            components.FieldSet(
                "Secrets",
                components.FieldSet.Field(
                    "Password",
                    components.Input(
                        default_value=LaunchLXCState.name,
                        type="password",
                        error="Must be between 8 to 64 characters",
                        min="8",
                        max="64",
                        name="password",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "SSH Key",
                    rx.text("Not currently supported", class_name="font-light italic"),
                ),
            ),
        )


class NetworkConfigurationPanel(EventGroup):
    """Panel for configuring LXC network settings."""

    @staticmethod
    @rx.event
    async def set_sector(state: LaunchLXCState, sector: str) -> None:
        """Set the network name for a specific network configuration."""
        state.sector = sector
        state.form_data["subnet"] = ""

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        return rx.fragment(
            components.FieldSet(
                "Sector Config",
                components.FieldSet.Field(
                    "Sector",
                    components.Select(
                        LaunchLXCState.sectors,
                        value=LaunchLXCState.sector,
                        on_change=cls.set_sector,
                        name="sector",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Subnet",
                    components.Select(
                        LaunchLXCState.subnets,
                        default_value=LaunchLXCState.subnet,
                        name="subnet",
                        required=True,
                    ),
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
                    components.DataList.Value(LaunchLXCState.name),
                ),
                components.DataList.Item(
                    components.DataList.Label("Appliance"),
                    components.DataList.Value(LaunchLXCState.appliance),
                ),
                components.DataList.Item(
                    components.DataList.Label("Root Store"),
                    components.DataList.Value(LaunchLXCState.rootfs),
                ),
                components.DataList.Item(
                    components.DataList.Label("Disk Size"),
                    components.DataList.Value(f"{LaunchLXCState.disk_size_gb}GB"),
                ),
                components.DataList.Item(
                    components.DataList.Label("Memory"),
                    components.DataList.Value(f"{LaunchLXCState.memory_gb}GiB ({LaunchLXCState.swap_gb}GiB Swap)"),
                ),
                components.DataList.Item(
                    components.DataList.Label("Cores"),
                    components.DataList.Value(f"{LaunchLXCState.cores}"),
                ),
                components.DataList.Item(
                    components.DataList.Label("Network"),
                    components.DataList.Value(LaunchLXCState.sector),
                ),
                components.DataList.Item(
                    components.DataList.Label("Subnet"),
                    components.DataList.Value(LaunchLXCState.subnet),
                ),
            ),
        )
