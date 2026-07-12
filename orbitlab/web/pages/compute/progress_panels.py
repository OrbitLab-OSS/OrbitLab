"""OrbitLab Progress Panels."""

from typing import Literal

import reflex as rx

from orbitlab.data_types import FrontendEvents, InstanceType, StorageContentType
from orbitlab.web import tailwind
from orbitlab.web.global_state import SelectOptions, SelectionDefaults
from orbitlab.web.utilities import EventGroup


class InstanceProgressPanelsState(rx.State):
    instance_type: rx.Field[Literal["lxc", "qemu"]] = rx.field(default="lxc")
    selected_node: rx.Field[str] = rx.field(default="")    

    @rx.event
    async def set_instance_type(self, instance_type: InstanceType) -> None:
        self.reset()
        self.instance_type = instance_type
        self.selected_node = await self.get_var_value(SelectionDefaults.default_node)


class InstanceComputeConfigurationPanel(EventGroup):

    @staticmethod
    @rx.event
    async def set_node(state: InstanceProgressPanelsState, node: str) -> FrontendEvents:
        state.selected_node = node
        if state.instance_type == "lxc":
            return rx.set_value("lxc-instance-disk-storage", "")
        return rx.set_value("vm-instance-disk-storage", "")

    def __new__(cls, instance_type: InstanceType | rx.vars.StringVar[InstanceType]) -> rx.Component:
        """Create and return the Progress Panel components."""
        storage_options = SelectOptions.node_storage_options.get(
            InstanceProgressPanelsState.selected_node, default={},
        ).to(dict)
        rootdir_options = storage_options.get(StorageContentType.ROOTDIR, default=[]).to(list[str])
        image_options = storage_options.get(StorageContentType.IMAGES, default=[]).to(list[str])
        return rx.el.div(
            tailwind.FieldSet(
                "Instance Configuration",
                tailwind.FieldSet.Field(
                    "Hostname: ",
                    tailwind.Input(
                        placeholder="my-compute",
                        auto_complete="off",
                        error="Names can be up to 64 alphanumeric characters, hyphens, and underscores.",
                        min="1",
                        max="64",
                        name="name",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                rx.cond(
                    InstanceProgressPanelsState.instance_type == "lxc",
                    tailwind.FieldSet.Field(
                        "Appliance: ",
                        tailwind.Select(
                            SelectOptions.all_appliance_options,
                            placeholder="Select Appliance",
                            name="base_id",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Image: ",
                        tailwind.Select(
                            SelectOptions.all_image_options,
                            placeholder="Select Image",
                            name="base_id",
                            required=True,
                            class_name="w-full",
                        ),
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
                rx.cond(
                    InstanceProgressPanelsState.instance_type == "qemu",
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
                    InstanceProgressPanelsState.instance_type == "lxc",
                    rx.fragment(
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
                ),
            ),
            tailwind.FieldSet(
                "Proxmox Configuration",
                tailwind.FieldSet.Field(
                    "Node: ",
                    tailwind.Select(
                        SelectOptions.node_options,
                        default_value=SelectionDefaults.default_node,
                        placeholder="Select Node",
                        on_change=cls.set_node,
                        name="node",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                rx.cond(
                    InstanceProgressPanelsState.instance_type == "lxc",
                    tailwind.FieldSet.Field(
                        "Disk Store: ",
                        tailwind.Select(
                            rootdir_options,
                            default_value=SelectionDefaults.default_rootdir_storage,
                            placeholder="Select Storage",
                            name="storage",
                            required=True,
                            class_name="w-full",
                            id="lxc-instance-disk-storage"
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Disk Store: ",
                        tailwind.Select(
                            image_options,
                            default_value=SelectionDefaults.default_images_storage,
                            placeholder="Select Storage",
                            name="storage",
                            required=True,
                            class_name="w-full",
                            id="vm-instance-disk-storage"
                        ),
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
            on_mount=InstanceProgressPanelsState.set_instance_type(instance_type),
            class_name="w-full h-full",
        )


class InstanceSecurityConfigurationPanel:

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        return rx.el.div(
            tailwind.FieldSet(
                "Password",
                tailwind.FieldSet.Field(
                    "Root Password",
                    tailwind.Input(
                        type="password",
                        error="Must be between 8 to 64 characters",
                        min="8",
                        max="64",
                        name="password",
                        class_name="w-full",
                    ),
                ),
                tailwind.FieldSet.Field(
                    "Confirm Password",
                    tailwind.Input(
                        type="password",
                        error="Must be between 8 to 64 characters",
                        min="8",
                        max="64",
                        name="password_confirmation",
                        class_name="w-full",
                    ),
                ),
                rx.el.div(
                    rx.text(
                        "If not provided, the password will be randomly generated.",
                        class_name="text-sm font-light opacity-50",
                    ),
                    class_name="w-full flex justify-end"
                ),
            ),
            tailwind.FieldSet(
                "SSH Keys",
                tailwind.FieldSet.Field(
                    "Key Pair",
                    rx.text("Not currently supported", class_name="font-light italic"),
                ),
            ),
            class_name="w-full h-full",
        )


class InstanceReviewPanel:
    def __new__(cls, form_data: rx.vars.ObjectVar[dict]) -> rx.Component:
        """Create and return the Progress Panel components."""
        cores = form_data.get("cores", default=0).to(int)
        sockets = form_data.get("sockets", default=0).to(int)
        vcpus = (cores * sockets).to(int)
        memory = form_data.get("memory").to(int)
        swap = form_data.get("swap", default=0).to(int)
        disk_size = form_data.get("disk_size").to(int)
        return rx.fragment(
            tailwind.DataList(
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Hostname"),
                    tailwind.DataList.Value(form_data.get("name")),
                ),
                tailwind.DataList.Item(
                    rx.cond(
                        InstanceProgressPanelsState.instance_type == "lxc",
                        tailwind.DataList.Label("Appliance"),
                        tailwind.DataList.Label("Image"),
                    ),
                    tailwind.DataList.Value(form_data.get("base_id")),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Disk Storage"),
                    tailwind.DataList.Value(form_data.get("storage")),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Disk Size"),
                    tailwind.DataList.Value(f"{disk_size} GB"),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Memory"),
                    rx.cond(
                        InstanceProgressPanelsState.instance_type == "lxc",
                        tailwind.DataList.Value(f"{memory} GiB ({swap} GiB Swap)"),
                        tailwind.DataList.Value(f"{memory} GiB"),
                    ),
                ),
                rx.cond(
                    InstanceProgressPanelsState.instance_type == "lxc",
                    tailwind.DataList.Item(
                        tailwind.DataList.Label("Cores"),
                        tailwind.DataList.Value(form_data.get("cores")),
                    ),
                    tailwind.DataList.Item(
                        tailwind.DataList.Label("vCPUs"),
                        tailwind.DataList.Value(f"{vcpus} ({cores} cores, {sockets} sockets)"),
                    ),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Sector"),
                    tailwind.DataList.Value(form_data.get("sector")),
                ),
            ),
        )
