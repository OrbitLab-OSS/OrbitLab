"""OrbitLab Launch LXC Progress Panels."""

import reflex as rx

from orbitlab.data_types import FrontendEvents, StorageContentType
from orbitlab.web import tailwind
from orbitlab.web.global_state import SelectOptions, SelectionDefaults
from orbitlab.web.utilities import EventGroup

from .states import LaunchLXCInstanceDialogState


class GeneralConfigurationPanel(EventGroup):
    """Panel for configuring general appliance settings."""

    @staticmethod
    @rx.event
    async def set_node(state: LaunchLXCInstanceDialogState, node: str) -> FrontendEvents:
        """Set the selected node and clear storage selection."""
        state.form_data["node"] = node
        return rx.set_value("lxc-instance-disk-storage", "")

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        selected_node = LaunchLXCInstanceDialogState.form_data.get("node", default=SelectionDefaults.default_node).to(str)
        storage_options = SelectOptions.node_storage_options.get(
            selected_node, default={},
        ).to(dict).get(StorageContentType.ROOTDIR, default=[]).to(list[str])
        return rx.fragment(
            tailwind.FieldSet(
                "Instance Configuration",
                tailwind.FieldSet.Field(
                    "Hostname: ",
                    tailwind.Input(
                        placeholder="my-lxc",
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
                    "Appliance: ",
                    tailwind.Select(
                        SelectOptions.all_appliance_options,
                        placeholder="Select Appliance",
                        name="appliance",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                tailwind.FieldSet.Field(
                    "Disk Size (Gb): ",
                    tailwind.Slider(
                        default_value=10,
                        min=8,
                        max=128,
                        name="disk_size",
                        required=True,
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
                tailwind.FieldSet.Field(
                    "Swap (GiB): ",
                    tailwind.Slider(
                        default_value=1,
                        min=1,
                        max=4,
                        name="swap",
                        required=True,
                    ),
                ),
                tailwind.FieldSet.Field(
                    "Enable NFS: ",
                    tailwind.Checkbox(name="nfs"),
                ),
            ),
            tailwind.FieldSet(
                "Proxmox Configuration",
                tailwind.FieldSet.Field(
                    "Node: ",
                    tailwind.Select(
                        SelectOptions.node_options,
                        default_value=selected_node,
                        placeholder="Select Node",
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
                        default_value=SelectionDefaults.default_rootdir_storage,
                        placeholder="Select Storage",
                        name="storage",
                        required=True,
                        class_name="w-full",
                        id="lxc-instance-disk-storage"
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
        memory = LaunchLXCInstanceDialogState.form_data.get("memory")
        swap = LaunchLXCInstanceDialogState.form_data.get("swap")
        disk_size = LaunchLXCInstanceDialogState.form_data.get("disk_size")
        return rx.fragment(
            tailwind.DataList(
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Hostname"),
                    tailwind.DataList.Value(LaunchLXCInstanceDialogState.form_data.get("name")),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Appliance"),
                    tailwind.DataList.Value(LaunchLXCInstanceDialogState.form_data.get("appliance")),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Storage"),
                    tailwind.DataList.Value(LaunchLXCInstanceDialogState.form_data.get("storage")),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Disk Size"),
                    tailwind.DataList.Value(f"{disk_size} GB"),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Memory"),
                    tailwind.DataList.Value(f"{memory} GiB ({swap} GiB Swap)"),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Cores"),
                    tailwind.DataList.Value(LaunchLXCInstanceDialogState.form_data.get("cores")),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Sector"),
                    tailwind.DataList.Value(LaunchLXCInstanceDialogState.form_data.get("sector")),
                ),
            ),
        )
