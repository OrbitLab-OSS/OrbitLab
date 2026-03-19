"""OrbitLab Create Custom Appliance Progress Panels."""

from pathlib import Path
from typing import Final, cast

import reflex as rx

from orbitlab.constants import Directories
from orbitlab.data_types import FrontendEvents, WorkflowStepType
from orbitlab.manifest.compute_templates.workflow_models import FileConfig, WorkflowStep
from orbitlab.web import components
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.pages.nodes.states import ProxmoxState
from orbitlab.web.utilities import EventGroup

from .states import CustomImageDialogState


class GeneralConfigurationPanel(EventGroup):
    """Panel for configuring general appliance settings."""

    @staticmethod
    @rx.event
    async def set_node(state: CustomImageDialogState, node: str) -> None:
        """Set the selected node and clear disk store selection."""
        state.form_data["node"] = node
        if "disk_store" in state.form_data:
            del state.form_data["disk_store"]

    @staticmethod
    @rx.event
    async def set_image_store(state: CustomImageDialogState, storage: str) -> None:
        """Set the selected image storage."""
        state.form_data["image_store"] = storage

    @staticmethod
    @rx.event
    async def set_disk_store(state: CustomImageDialogState, storage: str) -> None:
        """Set the selected disk storage."""
        state.form_data["disk_store"] = storage

    @staticmethod
    @rx.event
    async def set_sector(state: CustomImageDialogState, sector: str) -> None:
        """Set the sector name."""
        state.form_data["sector"] = sector
        if "subnet" in state.form_data:
            del state.form_data["subnet"]

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        return rx.fragment(
            components.FieldSet(
                "Proxmox",
                components.FieldSet.Field(
                    "Image Name: ",
                    components.Input(
                        placeholder="My Image",
                        default_value=CustomImageDialogState.name,
                        error="Names can be up to 128 characters.",
                        min="1",
                        max="128",
                        name="name",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                components.FieldSet.Field(
                    "Base Image: ",
                    components.Select(
                        CustomImageDialogState.base_images,
                        default_value=CustomImageDialogState.base_image,
                        placeholder="Select Base Image",
                        name="base_image",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                components.FieldSet.Field(
                    "Node: ",
                    components.Select(
                        ProxmoxState.node_names,
                        placeholder="Select Node",
                        default_value=ClusterDefaults.proxmox_node,
                        on_change=cls.set_node,
                        name="node",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                components.FieldSet.Field(
                    "Image Storage: ",
                    components.Select(
                        CustomImageDialogState.available_image_stores,
                        default_value=CustomImageDialogState.image_store,
                        on_change=cls.set_image_store,
                        placeholder="Select Storage",
                        name="image_store",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                components.FieldSet.Field(
                    "Temp Disk Store: ",
                    components.Select(
                        CustomImageDialogState.available_disk_stores,
                        default_value=CustomImageDialogState.disk_store,
                        on_change=cls.set_disk_store,
                        placeholder="Select Storage",
                        name="disk_store",
                        required=True,
                        class_name="w-full",
                    ),
                ),
                components.FieldSet.Field(
                    "Cores: ",
                    components.Slider(
                        default_value=CustomImageDialogState.cores,
                        min=1,
                        max=8,
                        name="cores",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Memory (GiB): ",
                    components.Slider(
                        default_value=CustomImageDialogState.memory_gb,
                        min=1,
                        max=12,
                        name="memory",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Disk Size (GiB): ",
                    components.Slider(
                        default_value=CustomImageDialogState.disk_size,
                        min=3,
                        max=10,
                        name="disk_size",
                        required=True,
                    ),
                ),
            ),
            components.FieldSet(
                "Network Configuration",
                components.FieldSet.Field(
                    "Sector",
                    components.Select(
                        CustomImageDialogState.available_sectors,
                        value=CustomImageDialogState.sector,
                        on_change=cls.set_sector,
                        required=True,
                        class_name="w-full",
                    ),
                ),
            ),
        )


class FilesWorkflowStep(EventGroup):
    """Workflow step for handling file uploads in custom appliance creation."""

    @staticmethod
    @rx.event
    async def handle_uploads(state: CustomImageDialogState, files: list[rx.UploadFile] | rx.upload_files) -> None:
        """Handle file uploads for workflow steps."""
        selected_files = cast("list[rx.UploadFile]", files)
        for index, step in state.steps_config.items():
            if step.type == WorkflowStepType.FILES and not step.files:
                uploaded_files: list[FileConfig] = []
                state.uploading = True
                for file in selected_files:
                    path: Path = Directories.CUSTOM_APPLIANCES / state.form_data["name"] / file.name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    data = await file.read()

                    with path.open("wb") as f:
                        f.write(data)
                    uploaded_files.append(FileConfig(source=path))
                state.steps_config[index].files = uploaded_files
                return

    @staticmethod
    @rx.event
    async def configure_files(state: CustomImageDialogState, step_id: int) -> FrontendEvents:
        """Configure files for a specific workflow step."""
        state.files_data = state.steps_config[step_id].files
        return components.Dialog.open(FilesWorkflowStep.dialog_id)

    @staticmethod
    @rx.event
    async def save_files(state: CustomImageDialogState, step_id: int, form: dict) -> FrontendEvents | None:
        """Save the configured files data to the workflow step and reset the dialog state."""
        if state.files_data:
            for file in state.files_data:
                file.destination = Path(form[str(file.source)])
            state.steps_config[step_id].files = state.files_data
            return FilesWorkflowStep.reset
        return None

    @staticmethod
    @rx.event
    def on_upload_progress(state: CustomImageDialogState, progress: dict) -> None:
        """Update the upload progress state based on the current upload progress."""
        max_percent = 100
        state.upload_progress = round(progress["progress"] * max_percent)
        if state.upload_progress >= max_percent:
            state.uploading = False

    @staticmethod
    @rx.event
    def cancel_upload(state: CustomImageDialogState) -> rx.event.EventSpec:
        """Cancel the current file upload operation."""
        state.uploading = False
        return rx.cancel_upload(FilesWorkflowStep.upload_id)

    @staticmethod
    @rx.event
    def reset(state: CustomImageDialogState) -> rx.event.EventCallback:
        """Cancel the current file upload operation."""
        state.files_data = None
        return components.Dialog.close(FilesWorkflowStep.dialog_id)

    dialog_id: Final = "custom-image-files-workflow-step-edit-dialog"
    upload_id: Final = "custom-image-files-workflow-step-upload"

    @classmethod
    def file(cls, form_id: str, file: FileConfig) -> rx.Component:
        """Create a file configuration component for workflow step files."""
        source = rx.Var.create(file.source).to(str)
        destination = rx.Var.create(file.destination).to(str)
        return rx.el.div(
            rx.el.div(
                rx.el.p("Source: "),
                components.Input(
                    value=source,
                    disabled=True,
                ),
                class_name="flex space-x-4",
            ),
            rx.el.div(
                rx.el.p("Destination: "),
                components.Input(
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
        step: WorkflowStep = CustomImageDialogState.steps_config.get(sort_id, {}).to(WorkflowStep)
        files = rx.Var.create(step.files).to(list[FileConfig])
        form_id = f"{sort_id}"
        return rx.el.div(
            rx.cond(
                CustomImageDialogState.uploading,
                rx.el.div(
                    components.Buttons.Primary("Cancel", on_click=cls.cancel_upload),
                    components.ProgressBars.Basic(value=CustomImageDialogState.upload_progress),
                    class_name="flex w-full items-center justify-center space-x-4",
                ),
                rx.cond(
                    files.to(bool),
                    rx.fragment(
                        components.Dialog(
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
                                components.Buttons.Secondary("Cancel", on_click=cls.reset),
                                components.Buttons.Primary("Save & Close", form=form_id),
                                class_name="w-full flex justify-end space-x-2 mt-10",
                            ),
                            dialog_id=cls.dialog_id,
                            class_name="max-w-[80vw] w-[80vw] max-h-[80vh] h-fit",
                        ),
                        components.Buttons.Primary(
                            "Configure Files",
                            on_click=cls.configure_files(sort_id),
                        ),
                    ),
                    components.UploadBox(
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
    """Workflow step for handling script execution in custom image creation."""

    @staticmethod
    @rx.event
    async def on_script_change(state: CustomImageDialogState, value: str) -> None:
        """Update the script data in state when the editor content changes."""
        state.script_value = value

    @staticmethod
    @rx.event
    async def save_script(state: CustomImageDialogState, step_id: int) -> rx.event.EventCallback:
        """Save the script data to the current step configuration and reset the dialog."""
        state.steps_config[step_id].script = state.script_value
        return ScriptWorkflowStep.reset

    @staticmethod
    @rx.event
    async def reset(state: CustomImageDialogState) -> rx.event.EventCallback:
        """Reset the script editing state by clearing script data and step ID."""
        state.script_value = state.default_script_value = ""
        return components.Dialog.close(ScriptWorkflowStep.dialog_id)

    @staticmethod
    @rx.event
    async def edit_script(state: CustomImageDialogState, step_id: int) -> rx.event.EventCallback:
        """Set the script step ID for editing."""
        state.script_value = state.default_script_value = state.steps_config[step_id].script or ""
        return components.Dialog.open(ScriptWorkflowStep.dialog_id)

    dialog_id: Final = "image-script-workflow-step-edit-dialog"

    def __new__(cls, sort_id: int | rx.Var[int]) -> rx.Component:
        """Create and return the Script workflow step."""
        return rx.el.div(
            components.Dialog(
                "Edit Workflow Script",
                rx.callout(
                    """
                    Scripts will be pushed to the '/tmp' directory on the LXC and executed from there.
                    After execution, they get deleted.
                    """,
                    icon="info",
                    class_name="my-2",
                ),
                components.Editor(
                    value=CustomImageDialogState.default_script_value,
                    on_change=cls.on_script_change,
                    language="shell",
                ),
                rx.el.div(
                    components.Buttons.Secondary("Cancel", on_click=cls.reset),
                    components.Buttons.Primary("Save & Close", on_click=cls.save_script(sort_id)),
                    class_name="w-full flex justify-end space-x-2 mt-10",
                ),
                dialog_id=cls.dialog_id,
                class_name="max-w-[80vw] w-[80vw] max-h-[80vh] h-fit",
            ),
            components.Buttons.Primary("Edit Script", on_click=cls.edit_script(sort_id)),
            class_name="flex grow items-center justify-center space-x-6",
        )


class WorkflowConfigurationPanel(EventGroup):
    """Panel for configuring workflow steps in custom image creation."""

    @staticmethod
    @rx.event
    async def add_step(state: CustomImageDialogState, step_type: str) -> None:
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
    async def delete_step(state: CustomImageDialogState, step_id: int) -> None:
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
    async def set_step_name(state: CustomImageDialogState, step_id: int, name: str) -> None:
        """Set the name for a workflow step."""
        state.steps_config[step_id].name = name

    @staticmethod
    @rx.event
    async def update_step_order(state: CustomImageDialogState, steps: list[components.SortableItem]) -> None:
        """Update the order of workflow steps."""
        state.step_order = steps

    @classmethod
    def sortable_step(cls, item: components.SortableItem) -> rx.Component:
        """Create a sortable workflow step component."""
        sort_id = rx.Var.create(item["id"]).to(int)
        step_config: WorkflowStep = CustomImageDialogState.steps_config.get(sort_id, {}).to(WorkflowStep)
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
                    components.Input(
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
                components.Buttons.Icon(
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
                components.Menu(
                    components.Buttons.Primary(
                        "Add Workflow Step",
                        icon="chevron-down",
                    ),
                    components.Menu.Item("Script Step", on_click=cls.add_step(WorkflowStepType.SCRIPT)),
                    components.Menu.Item("Files Step", on_click=cls.add_step(WorkflowStepType.FILES)),
                ),
                rx.text("Drag steps to change execution order."),
                class_name="w-full flex justify-between mb-4",
            ),
            components.Sortable(
                rx.foreach(CustomImageDialogState.step_order, lambda item: cls.sortable_step(item)),
                data=CustomImageDialogState.step_order,
                on_change=cls.update_step_order,
                class_name="mb-4 min-w-[50vw]",
            ),
        )


class ReviewPanel:
    """Panel for reviewing configuration before creation."""

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        return rx.fragment(
            rx.callout(
                rx.text(
                    "Any specified Root CAs will be added to the trust store ",
                    rx.el.span("before ", class_name="font-bold"),
                    rx.el.span("any of the Workflow Steps are executed."),
                ),
                icon="info",
                class_name="my-2",
            ),
            components.DataList(
                components.DataList.Item(
                    components.DataList.Label("Name"),
                    components.DataList.Value(CustomImageDialogState.name),
                ),
                components.DataList.Item(
                    components.DataList.Label("Base"),
                    components.DataList.Value(CustomImageDialogState.base_image),
                ),
                components.DataList.Item(
                    components.DataList.Label("Image Storage"),
                    components.DataList.Value(CustomImageDialogState.image_store),
                ),
                components.DataList.Item(
                    components.DataList.Label("Sector"),
                    components.DataList.Value(CustomImageDialogState.sector),
                ),
                components.DataList.Item(
                    components.DataList.Label("Workflow Steps"),
                    components.DataList.Value(
                        rx.el.div(
                            rx.foreach(
                                CustomImageDialogState.step_names_in_order,
                                lambda name, index: rx.text(f"Step {index}: {name}"),
                            ),
                            class_name="flex-col space-y-2",
                        ),
                    ),
                ),
            ),
        )
