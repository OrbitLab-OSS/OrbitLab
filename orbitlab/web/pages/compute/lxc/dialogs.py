"""OrbitLab LXC Dialogs."""

from typing import Final

import reflex as rx

from orbitlab.clients.proxmox.appliances import ApplianceInfo, ProxmoxAppliances
from orbitlab.data_types import ApplianceType, FrontendEvents
from orbitlab.manifest.appliances import BaseApplianceManifest, CustomApplianceManifest
from orbitlab.manifest.nodes import NodeManifest
from orbitlab.web import components
from orbitlab.web.components.feed import WorkflowFeed
from orbitlab.web.states.manifests import ClusterDefaults
from orbitlab.web.states.utilities import EventGroup

from .models import CreateCustomApplianceForm
from .progress_panels import (
    GeneralConfigurationPanel,
    NetworkConfigurationPanel,
    ReviewPanel,
    WorkflowConfigurationPanel,
)
from .states import CreateApplianceState, DownloadApplianceState


class DownloadApplianceDialog(EventGroup):
    """Dialog component for downloading appliance templates to Proxmox nodes."""

    @staticmethod
    @rx.event
    async def set_node(state: DownloadApplianceState, template: str, name: str) -> None:
        """Set the node for a template and update available storage options."""
        node_manifest = NodeManifest.load(name=name)
        state.download_configs[template].node = name
        state.download_configs[template].available_storage = [
            store.name for store in node_manifest.spec.storage if "vztmpl" in store.content
        ]

    @staticmethod
    @rx.event(background=True)
    async def start_appliance_download(_: rx.State, appliance: BaseApplianceManifest) -> FrontendEvents:
        """Wait for appliance download task to complete and update state."""
        await rx.run_in_thread(lambda: ProxmoxAppliances().download_appliance(appliance=appliance))
        return [
            DownloadApplianceState.cache_clear("base_appliances"),
            rx.toast.success(f"Appliance {appliance.name} download complete!"),
        ]

    @staticmethod
    @rx.event
    async def submit(state: DownloadApplianceState, form: dict) -> FrontendEvents:
        template: str = form["template"]
        node: str = form["node"]
        storage: str = form["storage"]
        # TODO: Fix
        # state.download_configs[template].downloading = True
        # appliance = next(iter(apl for apl in state.available_system_appliances if apl.template == template))
        # manifest = appliance.create_manifest(node=node, storage=storage)
        return [
            components.Dialog.close(DownloadApplianceDialog.dialog_id),
            # DownloadApplianceDialog.start_appliance_download(manifest),
        ]

    @staticmethod
    @rx.event
    async def set_appliance_view(state: DownloadApplianceState, appliance_view: str) -> None:
        """Set the current appliance view type (system or turnkey)."""
        state.appliance_view = ApplianceType(appliance_view)

    @staticmethod
    @rx.event
    async def search_appliances(state: DownloadApplianceState, query: str) -> None:
        """Set the search query string for filtering appliances."""
        state.query_string = query.lower()

    dialog_id: Final = "download-appliance-dialog"
    form_id: Final = "download-appliance-form"

    @classmethod
    def __appliance__(cls, appliance: ApplianceInfo) -> rx.Component:
        """Create a grid list item component for a system appliance."""
        return components.GridList.Item(
            rx.el.div(
                rx.el.div(
                    rx.el.h3(
                        appliance.template,
                        class_name=("text-lg font-semibold text-gray-900 dark:text-[#E8F1FF] truncate"),
                    ),
                    rx.el.p(
                        f"{appliance.type} • {appliance.version} • {appliance.architecture}",
                        class_name="text-sm text-gray-500 dark:text-gray-400 mt-1",
                    ),
                    class_name="mb-3",
                ),
                rx.el.p(
                    appliance.headline,
                    class_name="text-sm text-gray-700 dark:text-gray-300 line-clamp-3 mb-3",
                ),
            ),
            rx.el.div(
                rx.form(
                    rx.el.input(
                        form=f"form-{appliance.template}",
                        name="template",
                        value=appliance.template,
                        class_name="hidden",
                    ),
                    components.Select(
                        DownloadApplianceState.node_names,
                        default_value=ClusterDefaults.proxmox_node,
                        placeholder="Select Node",
                        name="node",
                        required=True,
                        on_change=lambda node: cls.set_node(appliance.template, node),
                    ),
                    # components.Select(
                    #     DownloadApplianceState.download_configs[appliance.template].available_storage,
                    #     placeholder="Select Storage",
                    #     name="storage",
                    #     required=True,
                    # ),
                    id=f"form-{appliance.template}",
                    on_submit=cls.submit,
                ),
                # rx.cond(
                #     DownloadApplianceState.download_configs[appliance.template].downloading,
                #     components.OrbitLabLogo(size=38, animated=True),
                #     components.Buttons.Primary("Download", form=f"form-{appliance.template}"),
                # ),
                class_name="flex flex-col items-center justify-center",
            ),
        )

    def __new__(cls) -> rx.Component:
        """Create and return the download appliance dialog component."""
        return components.Dialog(
            "Select Appliance to Download",
            rx.el.form(id=cls.form_id, on_submit=cls.submit),
            rx.el.div(
                # components.RadioGroup(
                #     components.RadioGroup.Item(
                #         "system",
                #         on_change=cls.set_appliance_view("system"),
                #         value=DownloadApplianceState.appliance_view,
                #     ),
                #     components.RadioGroup.Item(
                #         "turnkey",
                #         on_change=cls.set_appliance_view("turnkey"),
                #         value=DownloadApplianceState.appliance_view,
                #     ),
                # ),
                components.Input(placeholder="Search appliances...", icon="search", on_change=cls.search_appliances),
                class_name="flex items-center justify-between mb-4 space-x-4",
            ),
            rx.scroll_area(
                rx.vstack(
                    rx.match(
                        DownloadApplianceState.appliance_view,
                        (
                            ApplianceType.TURNKEY,
                            components.GridList(
                                rx.foreach(
                                    DownloadApplianceState.available_turnkey_appliances,
                                    lambda apl: cls.__appliance__(apl),
                                ),
                            ),
                        ),
                        components.GridList(
                            rx.foreach(
                                DownloadApplianceState.available_system_appliances,
                                lambda apl: cls.__appliance__(apl),
                            ),
                        ),
                    ),
                ),
                type="hover",
                scrollbars="vertical",
                class_name="flex-grow",
            ),
            rx.el.div(
                components.Buttons.Secondary("Close", on_click=components.Dialog.close(cls.dialog_id)),
                class_name="w-full flex justify-end mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[80vw] w-[80vw] max-h-[80vh] h-[80vh]",
        )


class CreateApplianceDialog(EventGroup):
    """Dialog for creating custom appliances from base appliances.

    This dialog provides a multi-step interface for users to create custom appliances
    by configuring general settings, defining workflow steps, and reviewing the final
    configuration before creation.
    """

    @staticmethod
    @rx.event
    async def create_appliance_from_base(state: CreateApplianceState, base_appliance: str) -> FrontendEvents:
        """Initialize appliance creation from a base appliance and open the dialog."""
        state.form_data["base_appliance"] = base_appliance
        return components.Dialog.open(CreateApplianceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def validate_general(state: CreateApplianceState, form: dict) -> FrontendEvents:
        """Update the form data with new values and proceed to the next step in the progress panel."""
        name = form["name"]
        form["memory"] = int(form["memory"])
        form["swap"] = int(form["swap"])
        if name in CustomApplianceManifest.get_existing():
            return rx.toast.error(f"Appliance with name '{name}' already exists.")
        state.form_data.update(form)
        return components.ProgressPanels.next(CreateApplianceDialog.progress_id)

    @staticmethod
    @rx.event
    async def validate_network(state: CreateApplianceState, form: dict) -> FrontendEvents:
        """Validate network configuration and proceed to the next step in the progress panel."""
        state.form_data.update(form)
        # TODO: Fix
        # for net in state.networks.values():
            # net.update()
        state.form_data["networks"] = [state.networks[item["id"]] for item in state.network_order]
        return components.ProgressPanels.next(CreateApplianceDialog.progress_id)

    @staticmethod
    @rx.event
    async def validate_wf_steps(state: CreateApplianceState, _: dict) -> FrontendEvents:
        """Validate all workflow steps in the appliance configuration."""
        steps = []
        for step in state.step_order:
            if not state.steps_config[step["id"]]:
                return rx.toast.error("All steps must be configured.")
            if error := state.steps_config[step["id"]].validate():
                step_name = state.steps_config[step["id"]].name or ""
                return rx.toast.error(f"Step {step_name}: {error}")
            steps.append(state.steps_config[step["id"]])
        state.form_data["workflow_steps"] = steps
        return components.ProgressPanels.next(CreateApplianceDialog.progress_id)

    @staticmethod
    @rx.event
    async def create_appliance(state: CreateApplianceState, form: dict) -> FrontendEvents:
        """Create the custom appliance with the configured settings and workflow steps."""
        state.form_data.update(form)
        form_data = CreateCustomApplianceForm.model_validate(state.form_data)
        form_data.generate_manifest().save()
        # TODO: Add event to initiate workflow and watch progress/logs
        return CreateApplianceDialog.reset

    @staticmethod
    @rx.event
    async def reset(state: CreateApplianceState) -> FrontendEvents:
        """Cancel the appliance creation process and reset the dialog state."""
        state.reset()
        return [
            components.Dialog.close(CreateApplianceDialog.dialog_id),
            components.ProgressPanels.reset(CreateApplianceDialog.progress_id),
        ]

    dialog_id: Final = "create-appliance-dialog"
    progress_id: Final = "create-appliance-progress-panels"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            "Create Custom Appliance",
            components.ProgressPanels(
                components.ProgressPanels.Step(
                    "General Configuration",
                    GeneralConfigurationPanel(),
                    validate=cls.validate_general,
                ),
                components.ProgressPanels.Step(
                    "Network Configuration",
                    NetworkConfigurationPanel(),
                    validate=cls.validate_network,
                ),
                components.ProgressPanels.Step(
                    "Workflow Steps",
                    WorkflowConfigurationPanel(),
                    validate=cls.validate_wf_steps,
                ),
                components.ProgressPanels.Step(
                    "Review & Verify",
                    ReviewPanel(),
                    validate=cls.create_appliance,
                ),
                cancel_button=components.Buttons.Secondary("Cancel", on_click=cls.reset),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )


# class RunApplianceWorkflowState(rx.State):
#     """State management for running custom appliance workflows.
    
#     This state class manages the execution of custom appliance workflows,
#     tracking the current appliance being processed and providing access
#     to its properties during the workflow execution.
#     """
#     appliance: CustomApplianceManifest | None = None

#     @rx.var
#     def name(self) -> str:
#         if self.appliance:
#             return self.appliance.name
#         return ""


# class RunCustomApplianceWorkflowDialog(EventGroup):

#     @staticmethod
#     @rx.event
#     async def run(state: RunApplianceWorkflowState, appliance: CustomApplianceManifest | dict) -> FrontendEvents:
#         if isinstance(appliance, dict):
#             appliance = CustomApplianceManifest.model_validate(appliance)
#         state.appliance = appliance
#         print(appliance)
#         return components.Dialog.open(RunCustomApplianceWorkflowDialog.dialog_id)

#     dialog_id: Final = "run-custom-appliance-workflow-dialog"

#     def __new__(cls) -> rx.Component:
#         """Create and return dialog component."""
#         return components.Dialog(
#             rx.text(
#                 "Running Workflow:",
#                 rx.el.span(
#                     components.Badge(RunApplianceWorkflowState.name, color_scheme="blue"),
#                     class_name="mx-2",
#                 ),
#             ),
#             WorkflowFeed(
#                 [
#                     {"title": "Create LXC", "description": "Initialize container from base template.", "status": "complete"},
#                     {"title": "Execute Steps", "description": "Run build scripts and copy files into LXC.", "status": "running"},
#                     {"title": "Convert to Template", "description": "Stop container and convert to template.", "status": "pending"},
#                     {"title": "Export Appliance", "description": "Archive template and upload to storage.", "status": "pending"},
#                     {"title": "Cleanup", "description": "Remove temporary LXC after upload confirmation.", "status": "pending"},
#                 ],
#             ),
#             dialog_id=cls.dialog_id,
#             class_name="max-w-[75vw] w-fit",
#             on_interact_outside=components.Dialog.close(cls.dialog_id),
#         )
