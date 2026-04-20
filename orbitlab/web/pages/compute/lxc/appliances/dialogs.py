"""OrbitLab LXC Dialogs."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Final

import reflex as rx
from reflex.event import EventCallback, EventSpec

from orbitlab.data_types import ApplianceType, FrontendEvents, StorageContentType, TemplateWorkflowStatus
from orbitlab.proxmox.compute_templates import ApplianceInfo
from orbitlab.redis.clients import ApplianceClient
from orbitlab.redis.models import BaseApplianceConfig, CustomApplianceConfig
from orbitlab.web import tailwind
from orbitlab.web.global_state import SelectionDefaults, SelectOptions
from orbitlab.web.utilities import EventGroup, create_workflow, get_redis_value

from .progress_panels import GeneralConfigurationPanel as CustomGeneralPanel
from .progress_panels import ReviewPanel as CustomReviewPanel
from .progress_panels import WorkflowConfigurationPanel
from .states import (
    CustomApplianceState,
    ApplianceWorkflowLogsViewDialogState,
    DeleteApplianceState,
    DownloadApplianceState,
)


class DownloadApplianceDialog(EventGroup):
    """Dialog component for downloading appliance templates to Proxmox nodes."""

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


class CustomApplianceDialog(EventGroup):
    """Dialog for creating and editing custom appliances from base appliances."""

    @staticmethod
    @rx.event
    async def start_appliance_creation(state: CustomApplianceState, base_appliance: str) -> FrontendEvents:
        """Initialize appliance creation from a base appliance and open the dialog."""
        state.form_data["base_appliance"] = base_appliance
        state.form_data["node"] = await state.get_var_value(SelectionDefaults.default_node)
        state.form_data["storage"] = await state.get_var_value(SelectionDefaults.default_vztmpl_storage)
        state.form_data["rootfs"] = await state.get_var_value(SelectionDefaults.default_rootdir_storage)
        return tailwind.Dialog.open(CustomApplianceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def validate_general(state: CustomApplianceState, form: dict) -> FrontendEvents:
        """Update the form data with new values and proceed to the next step in the progress panel."""
        form["memory"] = int(form["memory"])
        form["swap"] = int(form["swap"])
        state.form_data.update(form)
        return tailwind.ProgressPanels.next(CustomApplianceDialog.progress_id)

    @staticmethod
    @rx.event
    async def validate_wf_steps(state: CustomApplianceState, _: dict) -> FrontendEvents:
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
        return tailwind.ProgressPanels.next(CustomApplianceDialog.progress_id)

    @staticmethod
    @rx.event
    async def create_appliance(state: CustomApplianceState, form: dict) -> FrontendEvents:
        """Create the custom appliance with the configured settings and workflow steps."""
        state.form_data.update(form)
        client = ApplianceClient()
        appliance_id = await client.generate_appliance_id(appliance_type="custom")
        volume_id = await client.get_volume_id(id=state.form_data["base_appliance"])
        await client.set_appliance(
            appliance_type="custom",
            config=CustomApplianceConfig(
                id=appliance_id,
                name=state.form_data["name"],
                base_appliance_id=state.form_data["base_appliance"],
                volume_id=volume_id,
                node=state.form_data["node"],
                storage=state.form_data["rootfs"],
                cores=int(state.form_data["cores"]),
                memory=int(state.form_data["memory"]),
                swap=int(state.form_data["swap"]),
                sector=state.form_data["sector"],
                steps=state.form_data["workflow_steps"],
            )
        )
        return [
            CustomApplianceDialog.reset,
            CustomApplianceDialog.run_workflow(appliance_id),
        ]

    @staticmethod
    @rx.event
    async def run_workflow(_: rx.State, name: str) -> AsyncGenerator[EventSpec | EventCallback, None]:
        """Run the workflow for the specified custom appliance by name."""
        if error := await create_workflow(name="appliance.custom", version="v1", payload={"manifest": name}):
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Initiating {name} workflow..."),
            WorkflowLogsViewDialog.view_workflow_logs(name),
        ]

    @staticmethod
    @rx.event
    async def reset(state: CustomApplianceState) -> FrontendEvents:
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
                cancel_button=tailwind.Buttons.Secondary("Cancel", on_click=cls.reset),
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
        custom_appliances = await state.get_var_value(SelectOptions.custom_image_options)
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
        if error := await create_workflow(name="appliance.delete", version="v1", payload={"id": state.appliance_id, "appliance_type": state.appliance_type}):
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
                    "You are about to delete custom LXC appliance '",
                    rx.el.span(DeleteApplianceState.appliance_id, class_name="font-bold"),
                    rx.el.span(
                        """'. This will delete the manifest and the appliance from Proxmox Storage. Any existing
                        compute created from this appliance will not be affected.
                        """,
                    ),
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
        while state.countdown_refresh_seconds != 0:
            if not state.view_workflow:
                return
            async with state:
                state.countdown_refresh_seconds -= 1
            await asyncio.sleep(1)
        async with state:
            state.logs = await get_redis_value(name=f"ol:appliance:{state.view_workflow}", key="logs")
            state.countdown_refresh_seconds = 5
        status = await ApplianceClient().get_workflow_status(id=state.view_workflow)
        if status not in (TemplateWorkflowStatus.FAILED, TemplateWorkflowStatus.SUCCEEDED):
            state.workflow_running = True
            return [
                WorkflowLogsViewDialog.refresh_logs,
                rx.call_script(
                    "document.getElementById('custom-lxc-workflow-logs').scrollIntoView({ behavior: 'smooth', block: 'end' });"
                ),
            ]
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
