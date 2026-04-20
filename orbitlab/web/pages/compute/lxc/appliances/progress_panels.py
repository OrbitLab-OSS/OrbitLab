"""OrbitLab Create Custom Appliance Progress Panels."""

from pathlib import Path
from typing import Final, cast

import reflex as rx

from orbitlab.data_types import FrontendEvents, StorageContentType, WorkflowStepType
from orbitlab.web import tailwind
from orbitlab.web.global_state import SelectOptions, SelectionDefaults
from orbitlab.web.utilities import EventGroup
from orbitlab.worker.workflows.models import FileConfig, WorkflowStep

from .states import CustomApplianceState


class GeneralConfigurationPanel(EventGroup):
    """Panel for configuring general appliance settings."""

    @staticmethod
    @rx.event
    async def set_node(state: CustomApplianceState, node: str) -> FrontendEvents:
        """Set the selected node and clear storage selection."""
        state.form_data["node"] = node
        return [
            rx.set_value("custom-lxc-appliance-temp-storage", ""),
            rx.set_value("custom-lxc-appliance-storage", "")
        ]

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        selected_node = CustomApplianceState.form_data.get("node", default=SelectionDefaults.default_node).to(str)
        node_storage_options = SelectOptions.node_storage_options.get(
            selected_node, default="",
        ).to(dict[StorageContentType, list[str]])
        vztmpl_storage_options = node_storage_options.get(StorageContentType.VZTMPL, default=[]).to(list[str])
        rootdir_storage_options = node_storage_options.get(StorageContentType.ROOTDIR, default=[]).to(list[str])
        return rx.fragment(
            tailwind.FieldSet(
                "Appliance Configuration",
                tailwind.FieldSet.Field(
                    "Appliance Name: ",
                    tailwind.Input(
                        placeholder="My Appliance",
                        auto_complete="off",
                        default_value=CustomApplianceState.form_data.get("name", ""),
                        min="1",
                        max="128",
                        name="name",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                tailwind.FieldSet.Field(
                    "Base Appliance: ",
                    tailwind.Select(
                        SelectOptions.base_appliance_options,
                        default_value=CustomApplianceState.form_data.get("base_appliance", ""),
                        placeholder="Select Base Appliance",
                        name="base_appliance",
                        required=True,
                        class_name="w-full",
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
                    "Appliance Storage: ",
                    tailwind.Select(
                        vztmpl_storage_options,
                        default_value=CustomApplianceState.form_data.get("storage", SelectionDefaults.default_vztmpl_storage),
                        placeholder="Select Storage",
                        name="storage",
                        required=True,
                        class_name="w-full",
                        id="custom-lxc-appliance-storage"
                    ),
                ),
                tailwind.FieldSet.Field(
                    "Temp Disk Storage: ",
                    tailwind.Select(
                        rootdir_storage_options,
                        default_value=CustomApplianceState.form_data.get("rootfs", SelectionDefaults.default_rootdir_storage),
                        placeholder="Select Storage",
                        name="rootfs",
                        required=True,
                        class_name="w-full",
                        id="custom-lxc-appliance-temp-storage"
                    ),
                ),
            ),
            tailwind.FieldSet(
                "Machine Configuration",
                tailwind.FieldSet.Field(
                    "Sector",
                    tailwind.Select(
                        SelectOptions.sector_options,
                        value=CustomApplianceState.form_data.get("sector", ""),
                        name="sector",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                tailwind.FieldSet.Field(
                    "Memory (GiB): ",
                    tailwind.Slider(
                        default_value=CustomApplianceState.form_data.get("memory", 2).to(float),
                        min=1,
                        max=12,
                        name="memory",
                        required=True,
                    ),
                ),
                tailwind.FieldSet.Field(
                    "Swap (GiB): ",
                    tailwind.Slider(
                        default_value=CustomApplianceState.form_data.get("swap", 1).to(float),
                        min=1,
                        max=4,
                        name="swap",
                        required=True,
                    ),
                ),
            ),
        )


class FilesWorkflowStep(EventGroup):
    """Workflow step for handling file uploads in custom appliance creation."""

    @staticmethod
    @rx.event
    async def handle_uploads(state: CustomApplianceState, files: list[rx.UploadFile] | rx.upload_files) -> None:
        """Handle file uploads for workflow steps."""
        selected_files = cast("list[rx.UploadFile]", files)
        for index, step in state.steps_config.items():
            if step.type == WorkflowStepType.FILES and not step.files:
                uploaded_files: list[FileConfig] = []
                state.uploading = True
                for file in selected_files:
                    path: Path = state.form_data["name"] / file.name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    data = await file.read()

                    with path.open("wb") as f:
                        f.write(data)
                    uploaded_files.append(FileConfig(source=path))
                state.steps_config[index].files = uploaded_files
                return

    @staticmethod
    @rx.event
    async def configure_files(state: CustomApplianceState, step_id: int) -> FrontendEvents:
        """Configure files for a specific workflow step."""
        state.files_data = state.steps_config[step_id].files
        return tailwind.Dialog.open(FilesWorkflowStep.dialog_id)

    @staticmethod
    @rx.event
    async def save_files(state: CustomApplianceState, step_id: int, form: dict) -> FrontendEvents | None:
        """Save the configured files data to the workflow step and reset the dialog state."""
        if state.files_data:
            for file in state.files_data:
                file.destination = Path(form[str(file.source)])
            state.steps_config[step_id].files = state.files_data
            return FilesWorkflowStep.reset
        return None

    @staticmethod
    @rx.event
    def on_upload_progress(state: CustomApplianceState, progress: dict) -> None:
        """Update the upload progress state based on the current upload progress."""
        max_percent = 100
        state.upload_progress = round(progress["progress"] * max_percent)
        if state.upload_progress >= max_percent:
            state.uploading = False

    @staticmethod
    @rx.event
    def cancel_upload(state: CustomApplianceState) -> rx.event.EventSpec:
        """Cancel the current file upload operation."""
        state.uploading = False
        return rx.cancel_upload(FilesWorkflowStep.upload_id)

    @staticmethod
    @rx.event
    def reset(state: CustomApplianceState) -> rx.event.EventCallback:
        """Cancel the current file upload operation."""
        state.files_data = None
        return tailwind.Dialog.close(FilesWorkflowStep.dialog_id)

    dialog_id: Final = "files-workflow-step-edit-dialog"
    upload_id: Final = "files-workflow-step-upload"

    @classmethod
    def file(cls, form_id: str, file: FileConfig) -> rx.Component:
        """Create a file configuration component for workflow step files.

        Args:
            form_id: The form ID for the workflow step.
            file: The file push configuration object containing source and destination paths.

        Returns:
            A component with input fields for configuring file source and destination.
        """
        source = rx.Var.create(file.source).to(str)
        destination = rx.Var.create(file.destination).to(str)
        return rx.el.div(
            rx.el.div(
                rx.el.p("Source: "),
                tailwind.Input(
                    value=source,
                    disabled=True,
                ),
                class_name="flex space-x-4",
            ),
            rx.el.div(
                rx.el.p("Destination: "),
                tailwind.Input(
                    default_value=destination,
                    pattern=r"^\/(?:[A-Za-z0-9._\-]+(?:\/[A-Za-z0-9._\-]+)*)?$",
                    name=source,
                    form=form_id,
                    error="Destinations must be valid absolute file paths.",
                ),
                class_name="flex space-x-4",
            ),
            class_name="w-full flex flex-col space-y-2",
        )

    def __new__(cls, sort_id: int | rx.Var[int]) -> rx.Component:
        """Create and return the Files workflow step."""
        step: WorkflowStep = CustomApplianceState.steps_config.get(sort_id, {}).to(WorkflowStep)
        files = rx.Var.create(step.files).to(list[FileConfig])
        form_id = f"{sort_id}"
        return rx.el.div(
            rx.cond(
                CustomApplianceState.uploading,
                rx.el.div(
                    tailwind.Buttons.Primary("Cancel", on_click=cls.cancel_upload),
                    tailwind.ProgressBars.Basic(value=CustomApplianceState.upload_progress),
                    class_name="flex w-full items-center justify-center space-x-4",
                ),
                rx.cond(
                    files.to(bool),
                    rx.fragment(
                        tailwind.Dialog(
                            f"Configure Files Step: {step.name}",
                            rx.el.form(id=form_id, on_submit=lambda data: cls.save_files(sort_id, data)),
                            rx.callout(
                                """
                                Files must have a destination directory specified. You can also rename the file by
                                specifying the new file name (e.g. Destination: `/tmp/my_file.txt`).
                                """,
                                icon="info",
                                class_name="my-2",
                            ),
                            rx.el.div(
                                rx.foreach(files, lambda file: cls.file(form_id, file)),
                                class_name="divide-y divide-white/10",
                            ),
                            rx.el.div(
                                tailwind.Buttons.Secondary("Cancel", on_click=cls.reset),
                                tailwind.Buttons.Primary("Save & Close", form=form_id),
                                class_name="w-full flex justify-end space-x-2 mt-10",
                            ),
                            dialog_id=cls.dialog_id,
                            class_name="max-w-[80vw] w-[80vw] max-h-[80vh] h-fit",
                        ),
                        tailwind.Buttons.Primary(
                            "Configure Files",
                            on_click=cls.configure_files(sort_id),
                        ),
                    ),
                    tailwind.UploadBox(
                        upload_id=cls.upload_id,
                        on_drop=cls.handle_uploads(
                            rx.upload_files(upload_id=cls.upload_id, on_upload_progress=cls.on_upload_progress),
                        ),
                    ),
                ),
            ),
            class_name="flex grow items-center justify-center space-x-6",
        )


class ScriptWorkflowStep(EventGroup):
    """Workflow step for handling script execution in custom appliance creation.

    This class provides functionality for editing and managing bash scripts that will
    be executed as part of the appliance workflow steps during container creation.
    """

    @staticmethod
    @rx.event
    async def on_script_change(state: CustomApplianceState, value: str) -> None:
        """Update the script data in state when the editor content changes."""
        state.script_value = value

    @staticmethod
    @rx.event
    async def save_script(state: CustomApplianceState, step_id: int) -> rx.event.EventCallback:
        """Save the script data to the current step configuration and reset the dialog."""
        state.steps_config[step_id].script = state.script_value
        return ScriptWorkflowStep.reset

    @staticmethod
    @rx.event
    async def reset(state: CustomApplianceState) -> rx.event.EventCallback:
        """Reset the script editing state by clearing script data and step ID."""
        state.script_value = state.default_script_value = ""
        return tailwind.Dialog.close(ScriptWorkflowStep.dialog_id)

    @staticmethod
    @rx.event
    async def edit_script(state: CustomApplianceState, step_id: int) -> rx.event.EventCallback:
        """Set the script step ID for editing."""
        state.script_value = state.default_script_value = state.steps_config[step_id].script or ""
        return tailwind.Dialog.open(ScriptWorkflowStep.dialog_id)

    dialog_id: Final = "script-workflow-step-edit-dialog"

    def __new__(cls, sort_id: int | rx.Var[int]) -> rx.Component:
        """Create and return the Script workflow step."""
        return rx.el.div(
            tailwind.Dialog(
                "Edit Workflow Script",
                rx.callout(
                    """
                    Scripts will be pushed to the '/tmp' directory on the LXC and executed from there.
                    After execution, they get deleted.
                    """,
                    icon="info",
                    class_name="my-2",
                ),
                tailwind.Editor(
                    value=CustomApplianceState.default_script_value,
                    on_change=cls.on_script_change,
                    language="shell",
                ),
                rx.el.div(
                    tailwind.Buttons.Secondary("Cancel", on_click=cls.reset),
                    tailwind.Buttons.Primary("Save & Close", on_click=cls.save_script(sort_id)),
                    class_name="w-full flex justify-end space-x-2 mt-10",
                ),
                dialog_id=cls.dialog_id,
                class_name="max-w-[80vw] w-[80vw] max-h-[80vh] h-fit",
            ),
            tailwind.Buttons.Primary("Edit Script", on_click=cls.edit_script(sort_id)),
            class_name="flex grow items-center justify-center space-x-6",
        )


class WorkflowConfigurationPanel(EventGroup):
    """Panel for configuring workflow steps in custom appliance creation.

    This panel provides functionality for adding, configuring, and managing
    the order of workflow steps that will be executed during appliance creation.
    Users can add script and file push steps, configure their properties, and
    reorder them by dragging.
    """

    @staticmethod
    @rx.event
    async def add_step(state: CustomApplianceState, step_type: str) -> None:
        """Add a new workflow step to the appliance configuration."""
        new_item_id = len(state.step_order)
        while new_item_id in state.steps_config:
            new_item_id += 1
        state.step_order.append({"id": new_item_id})
        state.steps_config[new_item_id] = WorkflowStep(
            name=f"{step_type.capitalize()} {new_item_id}",
            type=WorkflowStepType(step_type),
        )

    @staticmethod
    @rx.event
    async def delete_step(state: CustomApplianceState, step_id: int) -> None:
        """Delete a workflow step from the appliance configuration."""
        files = state.steps_config[step_id].files
        if isinstance(files, list):
            for file in files:
                file.source.unlink(missing_ok=True)
        del state.steps_config[step_id]
        item = next((item for item in state.step_order if item["id"] == step_id), None)
        if item:
            state.step_order.remove(item)

    @staticmethod
    @rx.event
    async def set_step_name(state: CustomApplianceState, step_id: int, name: str) -> None:
        """Set the name for a workflow step in the appliance configuration."""
        state.steps_config[step_id].name = name

    @staticmethod
    @rx.event
    async def update_step_order(state: CustomApplianceState, steps: list[tailwind.SortableItem]) -> None:
        """Update the order of workflow steps in the appliance configuration."""
        state.step_order = steps

    @classmethod
    def sortable_step(cls, item: tailwind.SortableItem) -> rx.Component:
        """Create a sortable workflow step component."""
        sort_id = rx.Var.create(item["id"]).to(int)
        step_config: WorkflowStep = CustomApplianceState.steps_config.get(sort_id, {}).to(WorkflowStep)
        return rx.el.div(
            rx.icon(
                "grip-vertical",
                class_name=(
                    "drag-handle ml-3 mr-4 cursor-grab text-gray-500 dark:text-gray-400 "
                    "hover:text-[#1E63E9] dark:hover:text-[#36E2F4] "
                    "active:cursor-grabbing transition-colors duration-200 ease-in-out"
                ),
            ),
            rx.el.div(
                rx.el.div(
                    tailwind.Input(
                        value=step_config.name,
                        on_change=lambda name: cls.set_step_name(sort_id, name),
                        placeholder="Step Name (Required)",
                        wrapper_class_name="w-fit",
                    ),
                    class_name="flex space-x-4",
                ),
                rx.match(
                    step_config.type,
                    (
                        "script",
                        rx.el.div(
                            ScriptWorkflowStep(sort_id),
                            class_name="flex space-x-2 items-center justify-center",
                        ),
                    ),
                    (
                        "files",
                        rx.el.div(
                            FilesWorkflowStep(sort_id),
                            class_name="flex space-x-2 items-center justify-center",
                        ),
                    ),
                    rx.fragment(),
                ),
                tailwind.Buttons.Icon(
                    "trash",
                    on_click=lambda: cls.delete_step(sort_id),
                ),
                class_name="w-full flex items-center justify-between mx-4 space-x-4",
            ),
            key=sort_id,
            class_name=(
                "flex items-center gap-2 px-4 py-2 rounded-lg select-none "
                "border border-gray-200/60 dark:border-white/[0.08] "
                "bg-gradient-to-b from-gray-50/90 to-gray-100/80 "
                "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                "shadow-sm hover:shadow-md hover:ring-1 hover:ring-[#36E2F4]/30 "
                "transition-all duration-200 ease-in-out"
            ),
        )

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        return rx.fragment(
            rx.el.div(
                tailwind.Menu(
                    tailwind.Buttons.Primary(
                        "Add Workflow Step",
                        icon="chevron-down",
                    ),
                    tailwind.Menu.Item("Script Step", on_click=cls.add_step(WorkflowStepType.SCRIPT)),
                    tailwind.Menu.Item("Files Step", on_click=cls.add_step(WorkflowStepType.FILES)),
                ),
                rx.text("Drag steps to change execution order."),
                class_name="w-full flex justify-between mb-4",
            ),
            tailwind.Sortable(
                rx.foreach(CustomApplianceState.step_order, lambda item: cls.sortable_step(item)),
                data=CustomApplianceState.step_order,
                on_change=cls.update_step_order,
                class_name="mb-4 min-w-[50vw]",
            ),
        )


class ReviewPanel:
    """Panel for reviewing appliance configuration before creation.

    This panel displays a summary of all configured settings including
    general configuration, workflow steps, and certificate authorities
    for final review before creating the custom appliance.
    """

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        return rx.fragment(
            rx.callout(
                rx.text(
                    "Any specified Root CAs will be added to the LXC trust store ",
                    rx.el.span("before ", class_name="font-bold"),
                    rx.el.span("any of the Workflow Steps are executed."),
                ),
                icon="info",
                class_name="my-2",
            ),
            tailwind.DataList(
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Name"),
                    tailwind.DataList.Value(CustomApplianceState.form_data.get("name")),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Base"),
                    tailwind.DataList.Value(CustomApplianceState.form_data.get("base_appliance")),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Storage"),
                    tailwind.DataList.Value(CustomApplianceState.form_data.get("storage")),
                ),
                tailwind.DataList.Item(
                    tailwind.DataList.Label("Workflow Steps"),
                    tailwind.DataList.Value(
                        rx.el.div(
                            rx.foreach(
                                CustomApplianceState.step_names_in_order,
                                lambda name, index: rx.text(f"Step {index}: {name}"),
                            ),
                            class_name="flex-col space-y-2",
                        ),
                    ),
                ),
            ),
        )
