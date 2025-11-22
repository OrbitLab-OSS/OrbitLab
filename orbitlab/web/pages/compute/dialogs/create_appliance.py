from pathlib import Path
from typing import Final

import reflex as rx

from orbitlab.constants import WORKFLOW_FILES_ROOT
from orbitlab.data_types import CustomApplianceStepType, ManifestKind, StorageContentType
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.appliances import FilePush, Step
from orbitlab.web.components import (
    Buttons,
    Dialog,
    FieldSet,
    Popover,
    Input,
    MultiSelect,
    ProgressBars,
    Select,
    UploadBox,
    WithStatus,
)
from orbitlab.web.components.editor import Editor
from orbitlab.web.components.progress_panels import ProgressPanels
from orbitlab.web.components.sortable import Sortable, SortableItem
from orbitlab.web.states.certificates import CertificateManifestsState
from orbitlab.web.states.managers import ProgressPanelStateManager


class CreateApplianceState(CertificateManifestsState):
    form_data: dict = rx.field(default_factory=dict)
    step_order: list[SortableItem] = rx.field(default_factory=list)
    steps_config: dict[int, Step] = rx.field(default_factory=dict)
    uploading: bool = False
    upload_progress: int = 0
    script_value: str = ""

    @rx.var(cache=False)
    def base_appliances(self) -> list[str]:
        return list(ManifestClient().get_existing_by_kind(kind=ManifestKind.BASE_APPLIANCE).keys())

    @rx.var(cache=False)
    def nodes(self) -> list[str]:
        return list(ManifestClient().get_existing_by_kind(kind=ManifestKind.NODE))

    @rx.var
    def available_storage(self) -> list[str]:
        if self.node:
            node_manifest = ManifestClient().load(self.node, kind=ManifestKind.NODE)
            return [
                store.name for store in node_manifest.spec.storage.root if StorageContentType.VZTMPL in store.content
            ]
        return []

    @rx.var
    def step_types(self) -> list[str]:
        return list(CustomApplianceStepType)

    @rx.var
    def add_step_disabled(self) -> bool:
        for step in self.steps_config.values():
            if not step:
                return True
            if not step.valid:
                return True
        return False

    @rx.var
    def name(self) -> str:
        return self.form_data.get("name", "")

    @rx.var
    def base_appliance(self) -> str:
        return self.form_data.get("base_appliance", "")

    @rx.var
    def node(self) -> str:
        return self.form_data.get("node", "")

    @rx.var
    def storage(self) -> str:
        return self.form_data.get("storage", "")


@rx.event
async def create_appliance_from_base(state: CreateApplianceState, base_appliance: str) -> None:
    state.form_data["base_appliance"] = base_appliance
    return Dialog.open(CreateApplianceDialog.dialog_id)


@rx.event
async def cancel(state: CreateApplianceState):
    state.reset()
    return [
        Dialog.close(CreateApplianceDialog.dialog_id),
        ProgressPanelStateManager.reset_progress(CreateApplianceDialog.progress_id),
    ]


@rx.event
async def add_data_and_go_next(state: CreateApplianceState, form: dict) -> None:
    state.form_data.update(form)
    return ProgressPanelStateManager.next(CreateApplianceDialog.progress_id)


@rx.event
async def validate_workflow_steps(state: CreateApplianceState, form: dict) -> None:
    print(form)
    for step in state.step_order:
        if not state.steps_config[step["id"]]:
            return rx.toast.error("All steps must be configured.")
    print(state.steps_config)


@rx.event
async def set_node(state: CreateApplianceState, node: str):
    state.form_data["node"] = node
    if "storage" in state.form_data:
        del state.form_data["storage"]
        yield


@rx.event
async def set_storage(state: CreateApplianceState, storage: str):
    state.form_data["storage"] = storage


@rx.event
async def create_appliance(state: CreateApplianceState, form: dict):
    state.form_data.update(form)
    print(state.form_data)


@rx.event
async def update_step_order(state: CreateApplianceState, steps: list[SortableItem]):
    state.step_order = steps


@rx.event
async def add_step(state: CreateApplianceState):
    new_item_id = len(state.step_order)
    while new_item_id in state.steps_config:
        new_item_id += 1
    state.step_order.append({"id": new_item_id})
    state.steps_config[new_item_id] = {}


@rx.event
async def delete_step(state: CreateApplianceState, step_id: int):
    if hasattr(state.steps_config[step_id], "files"):
        for file in state.steps_config[step_id].files:
            file.source.unlink(missing_ok=True)
    del state.steps_config[step_id]
    item = next((item for item in state.step_order if item["id"] == step_id), None)
    state.step_order.remove(item)


@rx.event
async def set_step_type(state: CreateApplianceState, step_id: int, step_type: str):
    state.steps_config[step_id] = Step(type=CustomApplianceStepType(step_type))


@rx.event
async def set_step_name(state: CreateApplianceState, step_id: int, name: str):
    state.steps_config[step_id].name = name


@rx.event
async def handle_uploads(state: CreateApplianceState, files: list[rx.UploadFile]):
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


@rx.event
def on_upload_progress(state: CreateApplianceState, progress: dict):
    state.upload_progress = round(progress["progress"] * 100)
    if state.upload_progress >= 100:  # noqa: PLR2004
        state.uploading = False


@rx.event
def cancel_upload(state: CreateApplianceState):
    state.uploading = False
    return rx.cancel_upload(CreateApplianceDialog.upload_id)


@rx.event
async def set_destination(state: CreateApplianceState, step_id: int, source: str, destination: str):
    for file in state.steps_config[step_id].files:
        if file.source == Path(source):
            file.destination = Path(destination)
            break
            

@rx.event
async def set_script(state: CreateApplianceState, value: str):
    state.script_value = value


class ManageWorkflowStepScriptDialog:
    dialog_id: Final = "manage-workflow-step-script-dialog"

    def __new__(cls):
        return Dialog(
            "Edit Workflow Script",
            rx.callout(
                """
                Scripts will be pushed to the '/tmp' directory on the LXC and executed from there.
                After execution, they get deleted.
                """,
                icon="info",
                class_name="my-2"
            ),
            Editor(
                value=CreateApplianceState.script_value,
                on_change=set_script,
                language="shell",
            ),
            rx.el.div(
                Buttons.Primary(
                    "Save & Close",
                    on_click=Dialog.close(cls.dialog_id)
                ),
                class_name="w-full flex justify-end mt-10"
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[80vw] w-[80vw] max-h-[80vh] h-fit",
        )


class CreateApplianceDialog:
    dialog_id: Final = "create-appliance-dialog"
    progress_id: Final = "create-appliance-progress-panels"
    upload_id: Final = "create-dialog-file-upload"

    @classmethod
    def __files__(cls) -> rx.Component:
        return rx.el.div(
            rx.cond(
                CreateApplianceState.uploading,
                rx.el.div(
                    Buttons.Primary("Cancel", on_click=cancel_upload),
                    ProgressBars.Basic(value=CreateApplianceState.upload_progress),
                    class_name="flex w-full items-center justify-center space-x-4",
                ),
                rx.cond(
                    CreateApplianceState.steps_config.get(
                        Sortable.SortID.to(int),
                        {},
                    )
                    .get("files", None)
                    .is_none(),
                    UploadBox(
                        upload_id=cls.upload_id,
                        on_drop=handle_uploads(
                            rx.upload_files(upload_id=cls.upload_id, on_upload_progress=on_upload_progress),
                        ),
                    ),
                    Popover(
                        rx.el.div(
                            WithStatus(
                                rx.icon(
                                    "files",
                                    size=36,
                                    class_name=(
                                        "text-[#1E63E9] dark:text-[#36E2F4] "
                                        "transition-transform duration-300 ease-in-out "
                                        "group-hover:scale-110"
                                    ),
                                ),
                                status_content=CreateApplianceState.steps_config.get(
                                    Sortable.SortID.to(int),
                                    {},
                                )
                                .get("files", [])
                                .length(),
                                color="blue",
                            ),
                        ),
                        rx.foreach(
                            CreateApplianceState.steps_config.get(Sortable.SortID.to(int), {}).get("files", []),
                            lambda file: rx.el.div(
                                rx.el.div(
                                    rx.el.p("Source: "),
                                    Input(
                                        value=file["source"].to(str),
                                        disabled=True
                                    ),
                                    class_name="flex space-x-4"
                                ),
                                rx.el.div(
                                    rx.el.p("Destination: "),
                                    Input(
                                        value=file["destination"].to(str),
                                        pattern=r"^\/(?:[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)*)?$",
                                        on_change=lambda value: set_destination(Sortable.SortID, file["source"], value)
                                    ),
                                    class_name="flex space-x-4"
                                ),
                                class_name="w-fit flex flex-col space-y-2"
                            )
                        ),
                        side="bottom",
                        size="4",
                    ),
                ),
            ),
            class_name="flex grow items-center justify-center space-x-6",
        )

    @classmethod
    def __script__(cls) -> rx.Component:
        return rx.el.div(
            ManageWorkflowStepScriptDialog(),
            Buttons.Primary(
                "Edit Script",
                on_click=Dialog.open(ManageWorkflowStepScriptDialog.dialog_id)
            ),
            class_name="flex grow items-center justify-center space-x-6",
        )

    def __new__(cls) -> rx.Component:
        return Dialog(
            "Create Custom Appliance",
            ProgressPanels(
                ProgressPanels.Step(
                    "General Configuration",
                    FieldSet(
                        "Proxmox",
                        FieldSet.Field(
                            "Appliance Name: ",
                            Input(
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
                        FieldSet.Field(
                            "Base Appliance: ",
                            Select(
                                CreateApplianceState.base_appliances,
                                default_value=CreateApplianceState.base_appliance,
                                placeholder="Select Base Appliance",
                                name="base_appliance",
                                required=True,
                            ),
                        ),
                        FieldSet.Field(
                            "Node: ",
                            Select(
                                CreateApplianceState.nodes,
                                placeholder="Select Node",
                                default_value=CreateApplianceState.node,
                                on_change=set_node,
                                name="node",
                                required=True,
                            ),
                        ),
                        FieldSet.Field(
                            "Storage: ",
                            Select(
                                CreateApplianceState.available_storage,
                                value=CreateApplianceState.storage,
                                on_change=set_storage,
                                placeholder="Select Storage",
                                name="storage",
                                required=True,
                            ),
                        ),
                    ),
                    FieldSet(
                        "Certificates & Secrets",
                        FieldSet.Field(
                            "Root CAs",
                            MultiSelect(
                                CreateApplianceState.root_certificate_names,
                                placeholder="Select CAs",
                                name="certificate_authorities",
                                refresh_button=Buttons.Icon(
                                    "refresh-ccw",
                                    size=12,
                                    on_click=CertificateManifestsState.refresh_root_certificates,
                                ),
                            ),
                        ),
                        FieldSet.Field(
                            "SSH Key",
                            Input(
                                value="Auto-generated one-time key",
                                disabled=True,
                            ),
                        ),
                    ),
                    validate=add_data_and_go_next,
                ),
                ProgressPanels.Step(
                    "Workflow Steps",
                    rx.el.div(
                        Buttons.Primary(
                            "Add Workflow Step",
                            icon="plus",
                            on_click=add_step,
                            disabled=CreateApplianceState.add_step_disabled,
                        ),
                        rx.text("Drag steps to change execution order."),
                        class_name="w-full flex justify-between mb-4",
                    ),
                    Sortable(
                        Sortable.Item(
                            rx.el.div(
                                rx.el.div(
                                    rx.el.div(
                                        Input(
                                            value=CreateApplianceState.steps_config.get(
                                                Sortable.SortID.to(int),
                                                {},
                                            ).get("name", ""),
                                            on_change=lambda name: set_step_name(Sortable.SortID, name),
                                            placeholder="Step Name (Required)",
                                            wrapper_class_name="w-fit",
                                        ),
                                        Select(
                                            CreateApplianceState.step_types,
                                            value=CreateApplianceState.steps_config.get(
                                                Sortable.SortID.to(int),
                                                {},
                                            ).get("type", ""),
                                            on_change=lambda value: set_step_type(Sortable.SortID, value),
                                            placeholder="Select Step Type",
                                            name="workflow-steps",
                                            disabled=CreateApplianceState.uploading,
                                        ),
                                        class_name="flex space-x-4"
                                    ),
                                    rx.match(
                                        CreateApplianceState.steps_config.get(
                                            Sortable.SortID.to(int),
                                            {},
                                        ).get("type", ""),
                                        ("script", cls.__script__()),
                                        ("secrets", rx.el.p("secrets")),
                                        ("files", cls.__files__()),
                                        rx.fragment(),
                                    ),
                                    class_name="w-full flex items-center justify-between mx-4 space-x-4",
                                ),
                                Buttons.Icon("trash", on_click=lambda: delete_step(Sortable.SortID)),
                                class_name="w-full flex items-center justify-start",
                            ),
                        ),
                        data=CreateApplianceState.step_order,
                        on_change=update_step_order,
                        class_name="mb-4 min-w-[50vw]",
                    ),
                    # Custom Steps:
                    #   - Injected Secrets:
                    #       - Select multiple secrets from vault
                    #       - specify file path (name & location)
                    #       - Format (.env, JSON, YAML)
                    #   - ?
                    # Upload Files:
                    #   - User uploads N files (saved to file cache)
                    #   - Specify directory to place files in
                    # Run Script:
                    #   - User writes/uploads a custom bash script to execute
                    # > Can be done in any order and User may change order
                    validate=validate_workflow_steps,
                ),
                ProgressPanels.Step(
                    "Review & Verify",
                    # Show summarized data as a data list (compact)
                    rx.el.p("bar"),
                    validate=create_appliance,
                ),
                cancel_button=Buttons.Secondary("Cancel", on_click=cancel),
                id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit"
        )
