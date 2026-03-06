"""OrbitLab LXC Dialogs."""

from collections.abc import AsyncGenerator
from typing import Final

import reflex as rx
from reflex.event import EventCallback, EventSpec

from orbitlab.data_types import ApplianceType, FrontendEvents, StorageContentType
from orbitlab.manifest.compute_templates.appliances import BaseApplianceManifest, CustomApplianceManifest
from orbitlab.manifest.nodes import NodeManifest
from orbitlab.proxmox.compute_templates import ApplianceInfo
from orbitlab.web import components
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.utilities import EventGroup, get_worker

from .models import ApplianceItemDownload, CreateCustomApplianceForm
from .progress_panels import GeneralConfigurationPanel as CustomGeneralPanel
from .progress_panels import ReviewPanel as CustomReviewPanel
from .progress_panels import WorkflowConfigurationPanel
from .states import (
    CustomApplianceState,
    CustomApplianceTableState,
    DeleteApplianceState,
    DownloadApplianceState,
)


class DownloadApplianceDialog(EventGroup):
    """Dialog component for downloading appliance templates to Proxmox nodes."""

    @staticmethod
    @rx.event
    async def set_node(state: DownloadApplianceState, template: str, name: str) -> None:
        """Set the node for a template and update available storage options."""
        state.download_configs[template].node = name
        state.download_configs[template].available_storage = NodeManifest.load(
            name=name,
        ).list_storages(content_type=StorageContentType.VZTMPL)

    @staticmethod
    @rx.event
    async def submit(state: DownloadApplianceState, form: dict) -> FrontendEvents:
        """Handle the submission of the appliance download form."""
        template: str = form["template"]
        state.download_configs[template].downloading = True
        appliance = (
            next(iter(apl for apl in state.system_appliances if apl.template == template))
            if state.appliance_view == ApplianceType.SYSTEM
            else next(iter(apl for apl in state.turnkey_appliances if apl.template == template))
        )
        manifest = BaseApplianceManifest.create_from_appliance_info(
            node=form["node"],
            storage=form["storage"],
            appliance=appliance,
        )
        worker = get_worker()
        error = await worker.create_workflow(
            name="appliance.download",
            version="v1",
            payload={"manifest": manifest.name},
        )
        if error:
            return rx.toast.error(error)
        return [
            components.Dialog.close(DownloadApplianceDialog.dialog_id),
            rx.toast.info(f"Downloading {manifest.spec.template}..."),
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
                        DownloadApplianceState.nodes,
                        default_value=DownloadApplianceState.download_configs[appliance.template]
                        .to(ApplianceItemDownload)
                        .node,
                        placeholder="Select Node",
                        name="node",
                        required=True,
                        on_change=lambda node: cls.set_node(appliance.template, node),
                    ),
                    components.Select(
                        DownloadApplianceState.download_configs[appliance.template]
                        .to(ApplianceItemDownload)
                        .available_storage,
                        placeholder="Select Storage",
                        name="storage",
                        required=True,
                    ),
                    id=f"form-{appliance.template}",
                    on_submit=cls.submit,
                    class_name="flex-col space-y-2",
                ),
                rx.el.div(
                    rx.cond(
                        DownloadApplianceState.download_configs[appliance.template].to(ApplianceItemDownload).downloading,
                        components.OrbitLabLogo(size=38, animated=True),
                        components.Buttons.Primary("Download", form=f"form-{appliance.template}"),
                    ),
                    class_name="w-full flex items-center justify-center my-2"
                ),
                class_name="flex flex-col items-center justify-center",
            ),
        )

    dialog_id: Final = "download-appliance-dialog"
    form_id: Final = "download-appliance-form"

    def __new__(cls) -> rx.Component:
        """Create and return the download appliance dialog component."""
        return components.Dialog(
            "Select Appliance to Download",
            rx.el.form(id=cls.form_id, on_submit=cls.submit),
            rx.el.div(
                components.RadioGroup(
                    components.RadioGroup.Item(
                        "system",
                        on_change=cls.set_appliance_view("system"),
                        value=DownloadApplianceState.appliance_view,
                    ),
                    components.RadioGroup.Item(
                        "turnkey",
                        on_change=cls.set_appliance_view("turnkey"),
                        value=DownloadApplianceState.appliance_view,
                    ),
                ),
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
                                    DownloadApplianceState.turnkey_appliances,
                                    lambda apl: cls.__appliance__(apl),
                                ),
                            ),
                        ),
                        components.GridList(
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
                components.Buttons.Secondary("Close", on_click=components.Dialog.close(cls.dialog_id)),
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
        state.form_data["node"] = await state.get_var_value(ClusterDefaults.proxmox_node)
        state.form_data["storage"] = await state.get_var_value(ClusterDefaults.vztmpl_storage)
        state.form_data["rootfs"] = await state.get_var_value(ClusterDefaults.rootdir_storage)
        return components.Dialog.open(CustomApplianceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def validate_general(state: CustomApplianceState, form: dict) -> FrontendEvents:
        """Update the form data with new values and proceed to the next step in the progress panel."""
        if not state.edit_mode:
            name = form["name"]
            if name in CustomApplianceManifest.get_existing():
                return rx.toast.error(f"Appliance with name '{name}' already exists.")
        form["memory"] = int(form["memory"])
        form["swap"] = int(form["swap"])
        state.form_data.update(form)
        return components.ProgressPanels.next(CustomApplianceDialog.progress_id)

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
        return components.ProgressPanels.next(CustomApplianceDialog.progress_id)

    @staticmethod
    @rx.event
    async def create_appliance(state: CustomApplianceState, form: dict) -> FrontendEvents:
        """Create the custom appliance with the configured settings and workflow steps."""
        state.form_data.update(form)
        if state.edit_mode:
            manifest = CustomApplianceManifest.load(name=state.appliance_id)
            manifest.update(form_data=CreateCustomApplianceForm.model_validate(state.form_data))
        else:
            manifest = CustomApplianceManifest.create(
                form_data=CreateCustomApplianceForm.model_validate(state.form_data),
            )
        return [
            CustomApplianceDialog.reset,
            CustomApplianceDialog.run_workflow(manifest.name),
        ]

    @staticmethod
    @rx.event
    async def run_workflow(_: rx.State, name: str) -> AsyncGenerator[EventSpec | EventCallback, None]:
        """Run the workflow for the specified custom appliance by name."""
        worker = get_worker()
        error = await worker.create_workflow(
            name="appliance.custom",
            version="v1",
            payload={"manifest": name},
        )
        if error:
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
            components.Dialog.close(CustomApplianceDialog.dialog_id),
            components.ProgressPanels.reset(CustomApplianceDialog.progress_id),
        ]

    dialog_id: Final = "create-appliance-dialog"
    progress_id: Final = "create-appliance-progress-panels"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            CustomApplianceState.dialog_title,
            components.ProgressPanels(
                components.ProgressPanels.Step(
                    "General Configuration",
                    CustomGeneralPanel(),
                    validate=cls.validate_general,
                ),
                components.ProgressPanels.Step(
                    "Workflow Steps",
                    WorkflowConfigurationPanel(),
                    validate=cls.validate_wf_steps,
                ),
                components.ProgressPanels.Step(
                    "Review & Verify",
                    CustomReviewPanel(),
                    validate=cls.create_appliance,
                ),
                cancel_button=components.Buttons.Secondary("Cancel", on_click=cls.reset),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )


class DeleteApplianceDialog(EventGroup):
    """Delete an LXC Appliance."""

    @staticmethod
    @rx.event
    async def confirm(state: DeleteApplianceState, name: str) -> FrontendEvents:
        """Set appliance name to delete and open dialog."""
        state.reset()
        state.name = name
        if name in CustomApplianceManifest.get_existing():
            state.appliance_type = "custom"
        else:
            state.appliance_type = "base"
        return components.Dialog.open(DeleteApplianceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def update_confirmation(state: DeleteApplianceState, value: str) -> None:
        """Update the confirmation input text value."""
        state.confirmation = value

    @staticmethod
    @rx.event
    async def delete(state: DeleteApplianceState) -> FrontendEvents:
        """Delete a custom appliance from Proxmox and remove its manifest."""
        worker = get_worker()
        error = await worker.create_workflow(
            name="appliance.delete",
            version="v1",
            payload={"manifest": state.name, "appliance_type": state.appliance_type},
        )
        if error:
            return rx.toast.error(error)
        return [
            DeleteApplianceDialog.close,
            rx.toast.info(f"Deleting {state.name}..."),
        ]

    @staticmethod
    @rx.event
    async def close(state: DeleteApplianceState) -> FrontendEvents:
        """Cancel custom appliance deletion and close the dialog."""
        state.reset()
        return components.Dialog.close(DeleteApplianceDialog.dialog_id)

    dialog_id: Final = "confirm-delete-appliance-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return components.Dialog(
            f"Delete {DeleteApplianceState.name}",
            rx.el.div(
                rx.text(
                    "You are about to delete custom LXC appliance '",
                    rx.el.span(DeleteApplianceState.name, class_name="font-bold"),
                    rx.el.span(
                        """'. This will delete the manifest and the appliance from Proxmox Storage. Any existing
                        compute created from this appliance will not be affected.
                        """,
                    ),
                ),
                rx.text("If you are sure you want to delete this appliance, type its name below."),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            components.Input(
                placeholder=DeleteApplianceState.name,
                on_change=cls.update_confirmation,
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.close),
                components.Buttons.Primary(
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
    @rx.event
    async def view_workflow_logs(state: CustomApplianceTableState, name: str) -> FrontendEvents:
        """Set the workflow to view and open the dialog."""
        state.workflow_to_view = name
        return components.Dialog.open(WorkflowLogsViewDialog.dialog_id)

    @staticmethod
    @rx.event
    async def close(state: CustomApplianceTableState) -> FrontendEvents:
        """Close the dialog."""
        state.reset()
        return components.Dialog.close(WorkflowLogsViewDialog.dialog_id)

    dialog_id: Final = "appliance-workflow-logs-view-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return components.Dialog(
            f"{CustomApplianceTableState.workflow_to_view} Workflow Logs",
            rx.el.div(
                rx.code_block(
                    language="shell-session",
                    code=CustomApplianceTableState.logs,
                    code_tag_props={"style": {"whiteSpace": "pre-wrap"}},
                    show_line_numbers=True,
                ),
                class_name="w-full h-full overflow-auto",
            ),
            rx.el.div(
                components.Buttons.Secondary("Close", on_click=cls.close),
                class_name="w-full flex justify-end space-x-4 my-4",
            ),
            dialog_id=cls.dialog_id,
        )
