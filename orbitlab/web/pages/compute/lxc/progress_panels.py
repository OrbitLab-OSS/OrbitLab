"""OrbitLab LXC Progress Panels."""

from pathlib import Path
from typing import Final

import reflex as rx

from orbitlab.constants import WORKFLOW_FILES_ROOT
from orbitlab.data_types import CustomApplianceStepType
from orbitlab.manifest.schemas.appliances import FilePush, Step
from orbitlab.web import components
from orbitlab.web.states.certificates import CertificateManifestsState
from orbitlab.web.states.utilities import EventGroup

from .states import CreateApplianceState


class GeneralConfigurationPanel(EventGroup):
    """Panel for configuring general appliance settings.

    This panel provides form fields for configuring basic appliance properties
    including name, base appliance, node selection, storage, and certificate settings.
    """

    @staticmethod
    @rx.event
    async def set_node(state: CreateApplianceState, node: str) -> None:
        """Set the selected node and clear storage selection."""
        state.form_data["node"] = node
        if "storage" in state.form_data:
            del state.form_data["storage"]

    @staticmethod
    @rx.event
    async def set_storage(state: CreateApplianceState, storage: str) -> None:
        """Set the storage selection in the form data."""
        state.form_data["storage"] = storage

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        return rx.fragment(
            components.FieldSet(
                "Proxmox",
                components.FieldSet.Field(
                    "Appliance Name: ",
                    components.Input(
                        placeholder="my_custom_appliance",
                        default_value=CreateApplianceState.name,
                        pattern=r"(\w+)",
                        error="Names can be up to 64 alphanumeric characters and underscores.",
                        min="1",
                        max="64",
                        name="name",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Base Appliance: ",
                    components.Select(
                        CreateApplianceState.base_appliances,
                        default_value=CreateApplianceState.base_appliance,
                        placeholder="Select Base Appliance",
                        name="base_appliance",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Node: ",
                    components.Select(
                        CreateApplianceState.nodes,
                        placeholder="Select Node",
                        default_value=CreateApplianceState.node,
                        on_change=cls.set_node,
                        name="node",
                        required=True,
                    ),
                ),
                components.FieldSet.Field(
                    "Storage: ",
                    components.Select(
                        CreateApplianceState.available_storage,
                        value=CreateApplianceState.storage,
                        on_change=cls.set_storage,
                        placeholder="Select Storage",
                        name="storage",
                        required=True,
                    ),
                ),
            ),
            components.FieldSet(
                "Certificates & Secrets",
                components.FieldSet.Field(
                    "Root CAs",
                    components.MultiSelect(
                        CreateApplianceState.root_certificate_names,
                        placeholder="Select CAs",
                        name="certificate_authorities",
                        refresh_button=components.Buttons.Icon(
                            "refresh-ccw",
                            size=12,
                            on_click=CertificateManifestsState.refresh_root_certificates,
                        ),
                    ),
                ),
                components.FieldSet.Field(
                    "SSH Key",
                    rx.text("Auto-generated one-time key pair", class_name="font-light italic"),
                ),
            ),
        )


class FilesWorkflowStep(EventGroup):
    """Workflow step for handling file uploads in custom appliance creation.

    This class provides functionality for uploading files that will be pushed
    to specific locations within the LXC container during appliance creation.
    Users can upload multiple files and specify destination paths for each file.
    """

    @staticmethod
    @rx.event
    async def handle_uploads(state: CreateApplianceState, files: list[rx.UploadFile]) -> None:
        """Handle file uploads for workflow steps."""
        for index, step in state.steps_config.items():
            if step.type == CustomApplianceStepType.FILES and not step.files:
                uploaded_files: list[FilePush] = []
                state.uploading = True
                for file in files:
                    path: Path = WORKFLOW_FILES_ROOT / "custom_appliances" / state.form_data["name"] / file.name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    data = await file.read()

                    with path.open("wb") as f:
                        f.write(data)
                    uploaded_files.append(FilePush(source=path))
                state.steps_config[index].files = uploaded_files
                return

    @staticmethod
    @rx.event
    async def configure_files(state: CreateApplianceState, step_id: int) -> None:
        """Configure files for a specific workflow step."""
        state.files_step = step_id
        state.files_data = state.steps_config[state.files_step].files
        return components.Dialog.open(FilesWorkflowStep.dialog_id)

    @staticmethod
    @rx.event
    async def save_files(state: CreateApplianceState, form: dict) -> rx.event.EventCallback:
        """Save the configured files data to the workflow step and reset the dialog state."""
        for file in state.files_data:
            file.destination = Path(form[str(file.source)])
        state.steps_config[state.files_step].files = state.files_data
        return FilesWorkflowStep.reset

    @staticmethod
    @rx.event
    def on_upload_progress(state: CreateApplianceState, progress: dict) -> None:
        """Update the upload progress state based on the current upload progress."""
        max_percent = 100
        state.upload_progress = round(progress["progress"] * max_percent)
        if state.upload_progress >= max_percent:
            state.uploading = False

    @staticmethod
    @rx.event
    def cancel_upload(state: CreateApplianceState) -> rx.event.EventSpec:
        """Cancel the current file upload operation."""
        state.uploading = False
        return rx.cancel_upload(FilesWorkflowStep.upload_id)

    @staticmethod
    @rx.event
    def reset(state: CreateApplianceState) -> rx.event.EventCallback:
        """Cancel the current file upload operation."""
        state.files_step = None
        state.files_data = None
        return components.Dialog.close(FilesWorkflowStep.dialog_id)

    dialog_id: Final = "files-workflow-step-edit-dialog"
    upload_id: Final = "files-workflow-step-upload"

    @classmethod
    def file(cls, form_id: str, file: FilePush) -> rx.Component:
        """Create a file configuration component for workflow step files.

        Args:
            form_id: The form ID for the workflow step.
            file: The file push configuration object containing source and destination paths.

        Returns:
            A component with input fields for configuring file source and destination.
        """
        return rx.el.div(
            rx.el.div(
                rx.el.p("Source: "),
                components.Input(
                    value=rx.Var.create(file.source).to(str),
                    disabled=True,
                ),
                class_name="flex space-x-4",
            ),
            rx.el.div(
                rx.el.p("Destination: "),
                components.Input(
                    default_value=rx.Var.create(file.destination).to(str),
                    pattern=r"^\/(?:[A-Za-z0-9._\-]+(?:\/[A-Za-z0-9._\-]+)*)?$",
                    name=rx.Var.create(file.source).to(str),
                    form=form_id,
                    error="Destinations must be valid absolute file paths.",
                ),
                class_name="flex space-x-4",
            ),
            class_name="w-full flex flex-col space-y-2",
        )

    def __new__(cls) -> rx.Component:
        """Create and return the Files workflow step."""
        sort_id = components.Sortable.SortID.to(int)
        step_config = CreateApplianceState.steps_config.get(sort_id,{}).to(dict)
        step_name = step_config.get("name", "Unnamed").to(str)
        files = step_config.get("files", []).to(list[FilePush])
        form_id = f"{sort_id}"
        return rx.el.div(
            rx.cond(
                CreateApplianceState.uploading,
                rx.el.div(
                    components.Buttons.Primary("Cancel", on_click=cls.cancel_upload),
                    components.ProgressBars.Basic(value=CreateApplianceState.upload_progress),
                    class_name="flex w-full items-center justify-center space-x-4",
                ),
                rx.cond(
                    files.length() == 0,
                    components.UploadBox(
                        upload_id=cls.upload_id,
                        on_drop=cls.handle_uploads(
                            rx.upload_files(upload_id=cls.upload_id, on_upload_progress=cls.on_upload_progress),
                        ),
                    ),
                    rx.fragment(
                        components.Dialog(
                            f"Configure Files Step: {step_name}",
                            rx.el.form(id=form_id, on_submit=cls.save_files),
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
                        rx.cond(
                            step_config.get("valid", False),
                            rx.icon("check", class_name="text-green-500"),
                            rx.icon("info", class_name="text-red-500"),
                        ),
                        components.Buttons.Primary(
                            "Configure Files",
                            on_click=cls.configure_files(sort_id),
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
    async def on_script_change(state: CreateApplianceState, value: str) -> None:
        """Update the script data in state when the editor content changes."""
        state.script_data = value

    @staticmethod
    @rx.event
    async def save_script(state: CreateApplianceState) -> rx.event.EventCallback:
        """Save the script data to the current step configuration and reset the dialog."""
        state.steps_config[state.script_step].script = state.script_data
        return ScriptWorkflowStep.reset

    @staticmethod
    @rx.event
    async def reset(state: CreateApplianceState) -> rx.event.EventCallback:
        """Reset the script editing state by clearing script data and step ID."""
        state.script_data = ""
        state.script_step = None
        return components.Dialog.close(ScriptWorkflowStep.dialog_id)

    @staticmethod
    @rx.event
    async def edit_script(state: CreateApplianceState, step_id: int | None) -> rx.event.EventCallback:
        """Set the script step ID for editing."""
        state.script_step = step_id
        return components.Dialog.open(ScriptWorkflowStep.dialog_id)

    dialog_id: Final = "script-workflow-step-edit-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the Script workflow step."""
        sort_id = components.Sortable.SortID.to(int)
        steps_config = CreateApplianceState.steps_config.get(sort_id,{}).to(dict)
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
                    value=CreateApplianceState.default_script_value,
                    on_change=cls.on_script_change,
                    language="shell",
                ),
                rx.el.div(
                    components.Buttons.Secondary("Cancel", on_click=cls.reset),
                    components.Buttons.Primary("Save & Close", on_click=cls.save_script),
                    class_name="w-full flex justify-end space-x-2 mt-10",
                ),
                dialog_id=cls.dialog_id,
                class_name="max-w-[80vw] w-[80vw] max-h-[80vh] h-fit",
            ),
            rx.cond(
                steps_config.get("valid", False),
                rx.icon("check", class_name="text-green-500"),
                rx.icon("info", class_name="text-red-500"),
            ),
            components.Buttons.Primary("Edit Script", on_click=cls.edit_script(sort_id)),
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
    async def add_step(state: CreateApplianceState) -> None:
        """Add a new workflow step to the appliance configuration."""
        new_item_id = len(state.step_order)
        while new_item_id in state.steps_config:
            new_item_id += 1
        state.step_order.append({"id": new_item_id})
        state.steps_config[new_item_id] = {}

    @staticmethod
    @rx.event
    async def delete_step(state: CreateApplianceState, step_id: int) -> None:
        """Delete a workflow step from the appliance configuration."""
        if hasattr(state.steps_config[step_id], "files"):
            for file in state.steps_config[step_id].files:
                file.source.unlink(missing_ok=True)
        del state.steps_config[step_id]
        item = next((item for item in state.step_order if item["id"] == step_id), None)
        state.step_order.remove(item)

    @staticmethod
    @rx.event
    async def set_step_type(state: CreateApplianceState, step_id: int, step_type: str) -> None:
        """Set the type for a workflow step in the appliance configuration."""
        state.steps_config[step_id] = Step(type=CustomApplianceStepType(step_type))

    @staticmethod
    @rx.event
    async def set_step_name(state: CreateApplianceState, step_id: int, name: str) -> None:
        """Set the name for a workflow step in the appliance configuration."""
        state.steps_config[step_id].name = name

    @staticmethod
    @rx.event
    async def update_step_order(state: CreateApplianceState, steps: list[components.SortableItem]) -> None:
        """Update the order of workflow steps in the appliance configuration."""
        state.step_order = steps

    def __new__(cls) -> rx.Component:
        """Create and return the Progress Panel components."""
        sort_id = components.Sortable.SortID.to(int)
        step_config = CreateApplianceState.steps_config.get(sort_id,{}).to(dict)
        return rx.fragment(
            rx.el.div(
                components.Buttons.Primary(
                    "Add Workflow Step",
                    icon="plus",
                    on_click=cls.add_step,
                ),
                rx.text("Drag steps to change execution order."),
                class_name="w-full flex justify-between mb-4",
            ),
            components.Sortable(
                components.Sortable.Item(
                    rx.el.div(
                        rx.el.div(
                            components.Input(
                                value=step_config.get("name", ""),
                                on_change=lambda name: cls.set_step_name(sort_id, name),
                                placeholder="Step Name (Required)",
                                wrapper_class_name="w-fit",
                            ),
                            components.Select(
                                CreateApplianceState.step_types,
                                value=step_config.get("type", ""),
                                on_change=lambda value: cls.set_step_type(sort_id, value),
                                placeholder="Select Step Type",
                                name="workflow-steps",
                                disabled=CreateApplianceState.uploading,
                            ),
                            class_name="flex space-x-4",
                        ),
                        rx.match(
                            step_config.get("type", ""),
                            (
                                "script",
                                rx.el.div(
                                    ScriptWorkflowStep(),
                                    class_name="flex space-x-2 items-center justify-center",
                                ),
                            ),
                            (
                                "files",
                                rx.el.div(
                                    FilesWorkflowStep(),
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
                ),
                data=CreateApplianceState.step_order,
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
            components.DataList(
                components.DataList.Item(
                    components.DataList.Label("Name"),
                    components.DataList.Value(CreateApplianceState.name),
                ),
                components.DataList.Item(
                    components.DataList.Label("Base"),
                    components.DataList.Value(CreateApplianceState.base_appliance),
                ),
                components.DataList.Item(
                    components.DataList.Label("Storage"),
                    components.DataList.Value(CreateApplianceState.storage),
                ),
                components.DataList.Item(
                    components.DataList.Label("Root CAs"),
                    components.DataList.Value(
                        rx.cond(
                            CreateApplianceState.root_certs.length() > 0,
                            rx.foreach(
                                CreateApplianceState.root_certs,
                                lambda name: components.Badge(name, color_scheme="blue"),
                            ),
                            rx.text("N/A", class_name="font-light italic"),
                        ),
                    ),
                ),
                components.DataList.Item(
                    components.DataList.Label("SSH Key"),
                    components.DataList.Value(rx.text("Auto-generated", class_name="font-light italic")),
                ),
                components.DataList.Item(
                    components.DataList.Label("Workflow Steps"),
                    components.DataList.Value(
                        rx.el.div(
                            rx.foreach(
                                CreateApplianceState.step_names_in_order,
                                lambda name, index: rx.text(f"Step {index}: {name}"),
                            ),
                            class_name="flex-col space-y-2",
                        ),
                    ),
                ),
            ),
        )
