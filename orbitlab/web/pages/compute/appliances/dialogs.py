"""OrbitLab LXC Dialogs."""

import asyncio
from collections.abc import AsyncGenerator
import stat
from typing import Final

from pydantic import model_validator
import reflex as rx
from reflex.event import EventCallback, EventSpec

from orbitlab.data_types import ApplianceType, FrontendEvents, StorageContentType, TemplateWorkflowStatus
from orbitlab.proxmox import Proxmox
from orbitlab.proxmox.models import ApplianceInfo
from orbitlab.redis.clients import ApplianceClient
from orbitlab.redis.models import BaseApplianceConfig, CustomApplianceConfig
from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState, SelectionDefaults, SelectOptions
from orbitlab.web.utilities import EventGroup, create_workflow

from .progress_panels import GeneralConfigurationPanel as CustomGeneralPanel
from .progress_panels import ReviewPanel as CustomReviewPanel
from .progress_panels import WorkflowConfigurationPanel
from .states import (
    CustomApplianceState,
    ApplianceWorkflowLogsViewDialogState,
    DeleteApplianceState,
    DownloadApplianceState,
    PullOCIApplianceDialogState,
)


class DownloadApplianceDialog(EventGroup):
    """Dialog component for downloading appliance templates to Proxmox nodes."""

    @staticmethod
    @rx.event
    async def open(state: DownloadApplianceState) -> FrontendEvents:
        state.reset()
        default_node = await state.get_var_value(SelectionDefaults.default_node)
        bases = await state.get_var_value(OrbitLabState.base_appliances)
        existing = [apl.config.template for apl in bases]
        for appliance in await Proxmox().list_appliances():
            if appliance.template in existing:
                continue
            if appliance.is_turnkey:
                state.turnkey_appliances.append(appliance)
            else:
                state.system_appliances.append(appliance)
            state.download_configs[appliance.template] = default_node
        return tailwind.Dialog.open(DownloadApplianceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def set_node(state: DownloadApplianceState, template: str, name: str) -> None:
        """Set the node for a template."""
        state.download_configs[template] = name

    @staticmethod
    @rx.event
    async def submit(state: DownloadApplianceState, form: dict) -> FrontendEvents:
        """Handle the submission of the appliance download form."""
        appliance = (
            next(iter(apl for apl in state.system_appliances if apl.template == form["template"]))
            if state.appliance_view == ApplianceType.SYSTEM
            else next(iter(apl for apl in state.turnkey_appliances if apl.template == form["template"]))
        )
        client = ApplianceClient()
        appliance_id = await client.generate_appliance_id(appliance_type="base")
        await client.set_appliance(
            appliance_type="base",
            config=BaseApplianceConfig(
                id=appliance_id,
                node=form["node"],
                storage=form["storage"],
                template=appliance.template,
                description=appliance.description,
            )
        )
        if error := await create_workflow(name="appliance.download", version="v1", payload={"id": appliance_id}):
            return rx.toast.error(error)
        return [
            tailwind.Dialog.close(DownloadApplianceDialog.dialog_id),
            rx.toast.info(f"Downloading {appliance_id}..."),
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

    @classmethod
    def __appliance__(cls, appliance: ApplianceInfo) -> rx.Component:
        """Create a grid list item component for a system appliance."""
        selected_node = DownloadApplianceState.download_configs.get(appliance.template, default="").to(str)
        storage_options = SelectOptions.node_storage_options.get(selected_node, {}).to(dict).get(StorageContentType.VZTMPL, []).to(list[str])
        return tailwind.GridList.Item(
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
                    tailwind.Select(
                        SelectOptions.node_options,
                        default_value=SelectionDefaults.default_node,
                        placeholder="Select Node",
                        name="node",
                        required=True,
                        on_change=lambda node: cls.set_node(appliance.template, node),
                    ),
                    tailwind.Select(
                        storage_options,
                        default_value=SelectionDefaults.default_vztmpl_storage,
                        placeholder="Select Storage",
                        name="storage",
                        required=True,
                    ),
                    id=f"form-{appliance.template}",
                    on_submit=cls.submit,
                    class_name="flex-col space-y-2",
                ),
                rx.el.div(
                    tailwind.Buttons.Primary("Download", form=f"form-{appliance.template}"),
                    class_name="w-full flex items-center justify-center my-2"
                ),
                class_name="flex flex-col items-center justify-center",
            ),
        )

    dialog_id: Final = "download-appliance-dialog"
    form_id: Final = "download-appliance-form"

    def __new__(cls) -> rx.Component:
        """Create and return the download appliance dialog component."""
        return tailwind.Dialog(
            "Select Appliance to Download",
            rx.el.form(id=cls.form_id, on_submit=cls.submit),
            rx.el.div(
                tailwind.RadioGroup(
                    tailwind.RadioGroup.Item(
                        "system",
                        on_change=cls.set_appliance_view("system"),
                        value=DownloadApplianceState.appliance_view,
                    ),
                    tailwind.RadioGroup.Item(
                        "turnkey",
                        on_change=cls.set_appliance_view("turnkey"),
                        value=DownloadApplianceState.appliance_view,
                    ),
                ),
                tailwind.Input(placeholder="Search appliances...", icon="search", on_change=cls.search_appliances),
                class_name="flex items-center justify-between mb-4 space-x-4",
            ),
            rx.scroll_area(
                rx.vstack(
                    rx.match(
                        DownloadApplianceState.appliance_view,
                        (
                            ApplianceType.TURNKEY,
                            tailwind.GridList(
                                rx.foreach(
                                    DownloadApplianceState.turnkey_appliances,
                                    lambda apl: cls.__appliance__(apl),
                                ),
                            ),
                        ),
                        tailwind.GridList(
                            rx.foreach(
                                DownloadApplianceState.system_appliances,
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
                tailwind.Buttons.Secondary("Close", on_click=tailwind.Dialog.close(cls.dialog_id)),
                class_name="w-full flex justify-end mt-4",
            ),
            on_open=DownloadApplianceState.load,
            dialog_id=cls.dialog_id,
            class_name="max-w-[80vw] w-[80vw] max-h-[80vh] h-[80vh]",
        )


class PullOCIApplianceDialog(EventGroup):
    
    @staticmethod
    @rx.event
    async def open(state: PullOCIApplianceDialogState) -> FrontendEvents:
        state.node = await state.get_var_value(SelectionDefaults.default_node)
        return tailwind.Dialog.open(PullOCIApplianceDialog.dialog_id)
    
    @staticmethod
    @rx.event
    async def set_node(state: PullOCIApplianceDialogState, node: str) -> None:
        state.node = node
    
    @staticmethod
    @rx.event
    async def submit(_: rx.State, form: dict) -> FrontendEvents:
        client = ApplianceClient()
        
        form["id"] = await client.generate_appliance_id(appliance_type="base")
        form["oci"] = True
        config = BaseApplianceConfig.model_validate(form)
        await client.set_appliance(appliance_type="base", config=config)
        if error := await create_workflow(name="appliance.download", version="v1", payload={"id": config.id}):
            return rx.toast.error(error)
        return [
            PullOCIApplianceDialog.close,
            rx.toast.info(f"Downloading {config.id}..."),
        ]

    @staticmethod
    @rx.event
    async def close(state: PullOCIApplianceDialogState) -> FrontendEvents:
        state.reset()
        return tailwind.Dialog.close(PullOCIApplianceDialog.dialog_id)
    
    dialog_id: Final = "pull-oci-appliance-dialog"
    form_id: Final = "pull-oci-appliance-form"

    def __new__(cls) -> rx.Component:
        """Create and return the download appliance dialog component."""
        storage_options = SelectOptions.node_storage_options.get(
            PullOCIApplianceDialogState.node, default={},
        ).to(dict).get(StorageContentType.VZTMPL, []).to(list[str])
        return tailwind.Dialog(
            "Download OCI Container as Appliance",
            rx.el.form(
                tailwind.FieldSet(
                    "OCI Appliance Configuration",
                    tailwind.FieldSet.Field(
                        "Container Ref: ",
                        tailwind.Input(
                            placeholder="ghcr.io/repo/container:latest",
                            name="template",
                            form=cls.form_id,
                            required=True,
                            pattern=r"^(?:(?:[a-zA-Z\d]|[a-zA-Z\d][a-zA-Z\d-]*[a-zA-Z\d])(?:\.(?:[a-zA-Z\d]|[a-zA-Z\d][a-zA-Z\d-]*[a-zA-Z\d]))*(?::\d+)?/)?[a-z\d]+(?:(?:[._]|__|[-]*)[a-z\d]+)*(?:/[a-z\d]+(?:(?:[._]|__|[-]*)[a-z\d]+)*)*:\w[\w.-]{0,127}$",
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Description: ",
                        tailwind.Input(
                            name="description",
                            form=cls.form_id,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Node: ",
                        tailwind.Select(
                            SelectOptions.node_options,
                            default_value=SelectionDefaults.default_node,
                            placeholder="Select Node",
                            form=cls.form_id,
                            name="node",
                            required=True,
                            on_change=cls.set_node,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Storage: ",
                        tailwind.Select(
                            storage_options,
                            default_value=SelectionDefaults.default_vztmpl_storage,
                            placeholder="Select Storage",
                            form=cls.form_id,
                            name="storage",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.submit,
            ),
            rx.el.div(
                tailwind.Buttons.Primary("Submit", form=cls.form_id),
                tailwind.Buttons.Secondary("Close", on_click=tailwind.Dialog.close(cls.dialog_id)),
                class_name="w-full flex space-x-4 justify-end mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-[50vw] h-fit",
        )


class CustomApplianceDialog(EventGroup):
    """Dialog for creating and editing custom appliances from base appliances."""

    @staticmethod
    @rx.event
    async def start_appliance_creation(state: CustomApplianceState, base_appliance_id: str) -> FrontendEvents:
        """Initialize appliance creation from a base appliance and open the dialog."""
        state.form_data["base_appliance_id"] = base_appliance_id
        return tailwind.Dialog.open(CustomApplianceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def validate_general(state: CustomApplianceState, form: dict) -> FrontendEvents:
        """Update the form data with new values and proceed to the next step in the progress panel."""
        state.form_data.update(form)
        if "base_appliance_id" in state.form_data:
            state.form_data["base_volume_id"] = await ApplianceClient().get_volume_id(id=state.form_data["base_appliance_id"])
        return tailwind.ProgressPanels.next(CustomApplianceDialog.progress_id)

    @staticmethod
    @rx.event
    async def validate_wf_steps(state: CustomApplianceState, _: dict) -> FrontendEvents:
        """Validate all workflow steps in the appliance configuration."""
        for step in state.step_order:
            if not state.steps_config[step["id"]]:
                return rx.toast.error("All steps must be configured.")
            if error := state.steps_config[step["id"]].validate():
                step_name = state.steps_config[step["id"]].name or ""
                return rx.toast.error(f"Step {step_name}: {error}")
        return tailwind.ProgressPanels.next(CustomApplianceDialog.progress_id)

    @staticmethod
    @rx.event
    async def create_appliance(state: CustomApplianceState, form: dict) -> FrontendEvents:
        """Create the custom appliance with the configured settings and workflow steps."""
        state.form_data.update(form)
        state.form_data["steps"] = [step.to_step() for step in state.workflow_steps]
        
        client = ApplianceClient()
        if not "id" in state.form_data:
            state.form_data["id"] = await client.generate_appliance_id(appliance_type="custom")
        
        config = CustomApplianceConfig.model_validate(state.form_data)
        await client.set_appliance(appliance_type="custom", config=config)
        return [
            CustomApplianceDialog.close,
            CustomApplianceDialog.run_workflow(config.id),
        ]

    @staticmethod
    @rx.event
    async def run_workflow(_: rx.State, appliance_id: str) -> FrontendEvents:
        """Run the workflow for the specified custom appliance by appliance ID."""
        if error := await create_workflow(name="appliance.custom", version="v1", payload={"id": appliance_id}):
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Initiating {appliance_id} workflow..."),
            WorkflowLogsViewDialog.view_workflow_logs(appliance_id),
        ]

    @staticmethod
    @rx.event
    async def close(state: CustomApplianceState) -> FrontendEvents:
        """Cancel the appliance creation process and reset the dialog state."""
        state.reset()
        return [
            tailwind.Dialog.close(CustomApplianceDialog.dialog_id),
            tailwind.ProgressPanels.reset(CustomApplianceDialog.progress_id),
        ]

    dialog_id: Final = "create-appliance-dialog"
    progress_id: Final = "create-appliance-progress-panels"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
            CustomApplianceState.dialog_title,
            tailwind.ProgressPanels(
                tailwind.ProgressPanels.Step(
                    "General Configuration",
                    CustomGeneralPanel(),
                    validate=cls.validate_general,
                ),
                tailwind.ProgressPanels.Step(
                    "Workflow Steps",
                    WorkflowConfigurationPanel(),
                    validate=cls.validate_wf_steps,
                ),
                tailwind.ProgressPanels.Step(
                    "Review & Verify",
                    CustomReviewPanel(),
                    validate=cls.create_appliance,
                ),
                cancel_button=tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )


class DeleteApplianceDialog(EventGroup):
    """Delete an LXC Appliance."""

    @staticmethod
    @rx.event
    async def confirm(state: DeleteApplianceState, appliance_id: str) -> FrontendEvents:
        """Set appliance name to delete and open dialog."""
        state.reset()
        state.appliance_id = appliance_id
        custom_appliances = await state.get_var_value(SelectOptions.custom_appliance_options)
        if appliance_id in custom_appliances.values():
            state.appliance_type = "custom"
        else:
            state.appliance_type = "base"
        return tailwind.Dialog.open(DeleteApplianceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def update_confirmation(state: DeleteApplianceState, value: str) -> None:
        """Update the confirmation input text value."""
        state.confirmation = value

    @staticmethod
    @rx.event
    async def delete(state: DeleteApplianceState) -> FrontendEvents:
        """Delete a custom appliance from Proxmox and remove its manifest."""
        payload = {"id": state.appliance_id, "appliance_type": state.appliance_type}
        if error := await create_workflow(name="appliance.delete", version="v1", payload=payload):
            return rx.toast.error(error)
        return [
            DeleteApplianceDialog.close,
            rx.toast.info(f"Deleting {state.appliance_id}..."),
        ]

    @staticmethod
    @rx.event
    async def close(state: DeleteApplianceState) -> FrontendEvents:
        """Cancel custom appliance deletion and close the dialog."""
        state.reset()
        return tailwind.Dialog.close(DeleteApplianceDialog.dialog_id)

    dialog_id: Final = "confirm-delete-appliance-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return tailwind.Dialog(
            f"Delete {DeleteApplianceState.appliance_id}",
            rx.el.div(
                rx.text(
                    f"You are about to delete {DeleteApplianceState.appliance_type.capitalize()} LXC appliance ",
                    rx.el.span(DeleteApplianceState.appliance_id, class_name="font-bold"),
                    rx.el.span((
                        ". This will delete the configuration and the appliance from Proxmox Storage. Any existing "
                        "compute created from this appliance will not be affected."
                    )),
                ),
                rx.text("If you are sure you want to delete this appliance, type its name below."),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            tailwind.Input(
                placeholder=DeleteApplianceState.appliance_id,
                on_change=cls.update_confirmation,
            ),
            rx.el.div(
                tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                tailwind.Buttons.Primary(
                    "Delete",
                    disabled=DeleteApplianceState.delete_disabled,
                    on_click=cls.delete,
                ),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )


class WorkflowLogsViewDialog(EventGroup):
    """View custom appliance workflow logs."""

    @staticmethod
    @rx.event(background=True)
    async def refresh_logs(state: ApplianceWorkflowLogsViewDialogState) -> FrontendEvents | None:
        if state.view_workflow:
            client = ApplianceClient()
            
            while state.countdown_refresh_seconds != 0:
                if not state.view_workflow:
                    return
                async with state:
                    state.countdown_refresh_seconds -= 1
                await asyncio.sleep(1)
                
            async with state:
                state.logs = await client.get_workflow_logs(id=state.view_workflow)
                state.countdown_refresh_seconds = 5
                
            status = await client.get_workflow_status(id=state.view_workflow)
            if status not in (TemplateWorkflowStatus.FAILED, TemplateWorkflowStatus.SUCCEEDED):
                async with state:
                    state.workflow_running = True
                return [
                    WorkflowLogsViewDialog.refresh_logs,
                    rx.call_script(
                        "document.getElementById('custom-lxc-workflow-logs').scrollIntoView({ behavior: 'smooth', block: 'end' });"
                    ),
                ]
            async with state:
                state.workflow_running = False
            return rx.call_script(
                "document.getElementById('custom-lxc-workflow-logs').scrollIntoView({ behavior: 'smooth', block: 'end' });"
            )

    @staticmethod
    @rx.event
    async def view_workflow_logs(state: ApplianceWorkflowLogsViewDialogState, name: str) -> FrontendEvents:
        """Set the workflow to view and open the dialog."""
        state.view_workflow = name
        return [
            WorkflowLogsViewDialog.refresh_logs,
            tailwind.Dialog.open(WorkflowLogsViewDialog.dialog_id)
        ]

    @staticmethod
    @rx.event
    async def close(state: ApplianceWorkflowLogsViewDialogState) -> FrontendEvents:
        """Close the dialog."""
        state.view_workflow = ""
        state.workflow_running = False
        state.logs = ""
        state.countdown_refresh_seconds = 5
        return tailwind.Dialog.close(WorkflowLogsViewDialog.dialog_id)

    dialog_id: Final = "appliance-workflow-logs-view-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return tailwind.Dialog(
            f"{ApplianceWorkflowLogsViewDialogState.view_workflow} Workflow Logs",
            rx.el.div(
                rx.cond(
                    ApplianceWorkflowLogsViewDialogState.logs != "",
                    rx.code_block(
                        language="log",
                        code=ApplianceWorkflowLogsViewDialogState.logs,
                        code_tag_props={"style": {"whiteSpace": "pre-wrap"}},
                        show_line_numbers=False,
                        id=rx.Var.create("custom-lxc-workflow-logs"),
                    ),
                    rx.el.div(
                        tailwind.OrbitLabLogo(animated=True),
                        class_name="w-full h-full flex items-center justify-center"
                    ),
                ),
                class_name="w-full h-full overflow-auto",
            ),
            rx.el.div(
                tailwind.Buttons.Secondary(
                    rx.el.div(
                        "Close",
                        rx.cond(
                            ApplianceWorkflowLogsViewDialogState.workflow_running,
                            rx.progress(value=ApplianceWorkflowLogsViewDialogState.countdown_refresh_seconds, max=5),
                            rx.fragment(),
                        )
                    ),
                    on_click=cls.close,
                ),
                class_name="w-full flex justify-end space-x-4 my-4",
            ),
            dialog_id=cls.dialog_id,
        )


class Dialogs:
    def __new__(cls) -> rx.Component:
        return rx.fragment(
            DownloadApplianceDialog(),
            PullOCIApplianceDialog(),
            CustomApplianceDialog(),
            DeleteApplianceDialog(),
            WorkflowLogsViewDialog(),
        )
