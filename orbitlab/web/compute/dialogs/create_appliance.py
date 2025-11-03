from typing import Final
import reflex as rx
from pydantic import BaseModel, Field

from orbitlab.clients.proxmox.client import Proxmox
from orbitlab.clients.proxmox.models import ProxmoxApplianceInfo
from orbitlab.data_types import ApplianceType, ManifestKind
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.appliances import Step, BaseApplianceManifest
from orbitlab.manifest.schemas.nodes import NodeManifest
from orbitlab.web.components import FieldSet, Buttons, Input, GridList, OrbitLabLogo, Select
from orbitlab.web.components.progress_panels import ProgressPanels
from orbitlab.web.states.managers import DialogStateManager, ProgressPanelStateManager


class CreateApplianceState(rx.State):
    form_data: dict = rx.field(default_factory=dict)
    steps: list[Step] = rx.field(default_factory=list)

    @rx.var
    def base_appliances(self) -> list[str]:
        return list(ManifestClient().get_existing_by_kind(kind=ManifestKind.BASE_APPLIANCE))

    @rx.var
    def nodes(self) -> list[str]:
        return list(ManifestClient().get_existing_by_kind(kind=ManifestKind.NODE))
    
    @rx.var
    def available_storage(self) -> list[str]:
        if self.node:
            node_manifest = ManifestClient().load(self.node, kind=ManifestKind.NODE, model=NodeManifest)
            return [
                store.name for store in node_manifest.spec.storage if "vztmpl" in store.content
            ]
        return []

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
    return DialogStateManager.toggle(CreateApplianceDialog.dialog_id)


@rx.event
async def cancel(state: CreateApplianceState):
    state.reset()
    return [
        DialogStateManager.toggle(CreateApplianceDialog.dialog_id),
        ProgressPanelStateManager.reset_progress(CreateApplianceDialog.progress_id),
    ]


@rx.event
async def add_data_and_go_next(state: CreateApplianceState, form: dict) -> None:
    state.form_data.update(form)
    return ProgressPanelStateManager.next(CreateApplianceDialog.progress_id)


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


class CreateApplianceDialog:
    dialog_id: Final = "create-appliance-dialog"
    progress_id: Final = "create-appliance-progress-panels"

    def __new__(cls) -> rx.Component:
        return rx.dialog.root(
            rx.dialog.content(
                rx.dialog.title("Create Custom Appliance"),
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
                                    wrapper_class_name="grow"
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
                                    class_name="grow"
                                )
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
                                    class_name="grow"
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
                                    class_name="grow"
                                ),
                            ),
                        ),
                        FieldSet(
                            "Certificates & Secrets",
                            FieldSet.Field(
                                "Root CAs",
                                # Multi-Select from available CAs
                            ),
                            FieldSet.Field(
                                "SSH Key",
                                # Auto-generated default (for informational use only). Should get deleted on WF complete
                            ),
                        ),
                        validate=add_data_and_go_next
                    ),
                    ProgressPanels.Step(
                        "Workflow Steps",
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
                        rx.el.p("bar"),
                        validate=add_data_and_go_next
                    ),
                    ProgressPanels.Step(
                        "Review & Verify",
                        # Show summarized data as a data list (compact)
                        rx.el.p("bar"),
                        validate=create_appliance
                    ),
                    cancel_button=Buttons.Secondary("Cancel", on_click=cancel),
                    id=cls.progress_id,
                ),
                class_name="max-w-[85vw] w-fit max-h-[85vh] h-fit flex flex-col",
            ),
            on_mount=DialogStateManager.register(cls.dialog_id),
            open=DialogStateManager.registered.get(cls.dialog_id, False),
            class_name=(
                "border-r border-gray-200 dark:border-white/[0.08] "
                "transition-all duration-300 ease-in-out "
                "bg-gradient-to-b from-gray-50/95 to-gray-200/80 "
                "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)] "
                "hover:ring-1 hover:ring-[#36E2F4]/30"
            ),
        )
