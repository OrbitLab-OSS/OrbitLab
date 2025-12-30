"""OrbitLab LXC Dialogs."""

from collections.abc import AsyncGenerator
from typing import Final

import reflex as rx
from reflex.event import EventCallback, EventSpec

from orbitlab.clients.proxmox.appliances import ApplianceInfo, ProxmoxAppliances
from orbitlab.clients.proxmox.compute.client import ProxmoxCompute
from orbitlab.data_types import ApplianceType, CustomApplianceWorkflowStatus, FrontendEvents, StorageContentType
from orbitlab.manifest.appliances import BaseApplianceManifest, CustomApplianceManifest
from orbitlab.manifest.lxc import LXCManifest
from orbitlab.manifest.nodes import NodeManifest
from orbitlab.web import components
from orbitlab.web.states.manifests import ManifestsState
from orbitlab.web.states.utilities import EventGroup

from .custom_appliance_progress_panels import GeneralConfigurationPanel as CustomGeneralPanel
from .custom_appliance_progress_panels import NetworkConfigurationPanel as CustomNetworkPanel
from .custom_appliance_progress_panels import ReviewPanel as CustomReviewPanel
from .custom_appliance_progress_panels import WorkflowConfigurationPanel
from .launch_progress_panels import GeneralConfigurationPanel, NetworkConfigurationPanel, ReviewPanel
from .models import ApplianceItemDownload, CreateCustomApplianceForm, CreateLXCForm
from .states import CustomApplianceState, DeleteCustomApplianceState, DownloadApplianceState, LaunchLXCState


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
    @rx.event(background=True)
    async def start_appliance_download(_: rx.State, appliance: BaseApplianceManifest) -> FrontendEvents:
        """Wait for appliance download task to complete and update state."""
        await rx.run_in_thread(lambda: ProxmoxAppliances().download_appliance(appliance=appliance))
        return [
            ManifestsState.cache_clear("base_appliances"),
            rx.toast.success(f"Appliance {appliance.name} download complete!"),
        ]

    @staticmethod
    @rx.event
    async def submit(state: DownloadApplianceState, form: dict) -> FrontendEvents:
        """Handle the submission of the appliance download form."""
        template: str = form["template"]
        node_ref = NodeManifest.load(name=form["node"]).to_ref()
        state.download_configs[template].downloading = True
        appliance = next(iter(apl for apl in state.system_appliances if apl.template == template)) \
            if state.appliance_view == ApplianceType.SYSTEM else \
                next(iter(apl for apl in state.turnkey_appliances if apl.template == template))
        manifest = BaseApplianceManifest.create_from_appliance_info(
            node_ref=node_ref,
            storage=form["storage"],
            appliance=appliance,
        )
        return [
            components.Dialog.close(DownloadApplianceDialog.dialog_id),
            DownloadApplianceDialog.start_appliance_download(manifest),
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
                        DownloadApplianceState.nodes,
                        default_value=DownloadApplianceState.download_configs[appliance.template].to(ApplianceItemDownload).node,
                        placeholder="Select Node",
                        name="node",
                        required=True,
                        on_change=lambda node: cls.set_node(appliance.template, node),
                    ),
                    components.Select(
                        DownloadApplianceState.download_configs[appliance.template].to(ApplianceItemDownload).available_storage,
                        placeholder="Select Storage",
                        name="storage",
                        required=True,
                    ),
                    id=f"form-{appliance.template}",
                    on_submit=cls.submit,
                ),
                rx.cond(
                    DownloadApplianceState.download_configs[appliance.template].to(ApplianceItemDownload).downloading,
                    components.OrbitLabLogo(size=38, animated=True),
                    components.Buttons.Primary("Download", form=f"form-{appliance.template}"),
                ),
                class_name="flex flex-col items-center justify-center",
            ),
        )

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


class DeleteConfirmationDialog(EventGroup):
    """Confirmation dialog for deleting custom appliances."""

    @staticmethod
    @rx.event(background=True)
    async def delete_appliance(state: DeleteCustomApplianceState) -> FrontendEvents:
        """Delete a custom appliance from Proxmox and remove its manifest."""
        appliance = CustomApplianceManifest.load(name=state.name)
        await rx.run_in_thread(lambda: ProxmoxAppliances().delete_custom_appliance(appliance=appliance))
        appliance.delete()
        return [
            ManifestsState.cache_clear("custom_appliances"),
            rx.toast.success(f"Appliance '{appliance.name}' successfully deleted."),
        ]

    @staticmethod
    @rx.event
    async def confirm_deletion(state: DeleteCustomApplianceState, name: str) -> FrontendEvents:
        """Set the custom appliance name and open the dialog."""
        state.name = name
        return components.Dialog.open(DeleteConfirmationDialog.dialog_id)

    @staticmethod
    @rx.event
    async def update_confirmation(state: DeleteCustomApplianceState, value: str) -> None:
        """Update the confirmation input text value."""
        state.confirmation = value

    @staticmethod
    @rx.event
    async def cancel(state: DeleteCustomApplianceState) -> FrontendEvents:
        """Cancel custom appliance deletion and close the dialog."""
        state.reset()
        return components.Dialog.close(DeleteConfirmationDialog.dialog_id)

    dialog_id: Final = "confirm-delete-custom-appliance-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return components.Dialog(
            f"Delete {DeleteCustomApplianceState.name}",
            rx.el.div(
                rx.text(
                    "You are about to delete custom LXC appliance '",
                    rx.el.span(DeleteCustomApplianceState.name, class_name="font-bold"),
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
                placeholder=DeleteCustomApplianceState.name,
                on_change=cls.update_confirmation,
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.cancel),
                components.Buttons.Primary(
                    "Delete",
                    disabled=DeleteCustomApplianceState.delete_disabled,
                    on_click=[
                        components.Dialog.close(cls.dialog_id),
                        cls.delete_appliance,
                    ],
                ),
                class_name="w-full flex justify-end space-x-4",
            ),
            dialog_id=cls.dialog_id,
        )


class CustomApplianceDialog(EventGroup):
    """Dialog for creating and editing custom appliances from base appliances."""

    @staticmethod
    @rx.event
    async def create_appliance_from_base(state: CustomApplianceState, base_appliance: str) -> FrontendEvents:
        """Initialize appliance creation from a base appliance and open the dialog."""
        state.form_data["base_appliance"] = base_appliance
        return components.Dialog.open(CustomApplianceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def validate_general(state: CustomApplianceState, form: dict) -> FrontendEvents:
        """Update the form data with new values and proceed to the next step in the progress panel."""
        name = form["name"]
        form["memory"] = int(form["memory"])
        form["swap"] = int(form["swap"])
        if name in CustomApplianceManifest.get_existing():
            return rx.toast.error(f"Appliance with name '{name}' already exists.")
        state.form_data.update(form)
        return components.ProgressPanels.next(CustomApplianceDialog.progress_id)

    @staticmethod
    @rx.event
    async def validate_network(state: CustomApplianceState, form: dict) -> FrontendEvents:
        """Validate network configuration and proceed to the next step in the progress panel."""
        state.form_data.update(form)
        state.form_data["networks"] = [state.networks[item["id"]] for item in state.network_order]
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
        manifest = CustomApplianceManifest.create(
            form=CreateCustomApplianceForm.model_validate(state.form_data),
        )
        return [
            CustomApplianceDialog.reset,
            CustomApplianceDialog.run_workflow(manifest.name),
        ]

    @staticmethod
    @rx.event(background=True)
    async def run_workflow(_: rx.State, name: str) -> AsyncGenerator[EventSpec | EventCallback, None]:
        """Run the workflow for the specified custom appliance by name."""
        appliance = CustomApplianceManifest.load(name=name)
        appliance.set_workflow_status(status=CustomApplianceWorkflowStatus.PENDING)
        yield ManifestsState.cache_clear("custom_appliances")
        await rx.run_in_thread(lambda: ProxmoxAppliances().run_workflow(appliance=appliance))
        yield rx.toast.success(f"Appliance {appliance.name} workflow complete!")
        yield ManifestsState.cache_clear("custom_appliances")


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
            "Create Custom Appliance",
            components.ProgressPanels(
                components.ProgressPanels.Step(
                    "General Configuration",
                    CustomGeneralPanel(),
                    validate=cls.validate_general,
                ),
                components.ProgressPanels.Step(
                    "Network Configuration",
                    CustomNetworkPanel(),
                    validate=cls.validate_network,
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


class LaunchApplianceDialog(EventGroup):
    """Dialog for launching LXC appliances."""

    @staticmethod
    @rx.event
    async def validate_general(state: LaunchLXCState, form: dict) -> FrontendEvents:
        """Update the form data with new values and proceed to the next step in the progress panel."""
        form["memory"] = int(form["memory"])
        form["swap"] = int(form["swap"])
        form["cores"] = int(form["cores"])
        form["disk_size"] = int(form["disk_size"])
        state.form_data.update(form)
        return components.ProgressPanels.next(LaunchApplianceDialog.progress_id)

    @staticmethod
    @rx.event
    async def validate_network(state: LaunchLXCState, form: dict) -> FrontendEvents:
        """Validate network configuration and proceed to the next step in the progress panel."""
        state.form_data.update(form)
        return components.ProgressPanels.next(LaunchApplianceDialog.progress_id)

    @staticmethod
    @rx.event
    async def create_lxc(state: LaunchLXCState, form: dict) -> FrontendEvents:
        """Create the custom appliance with the configured settings and workflow steps."""
        state.form_data.update(form)
        form_data = CreateLXCForm.model_validate(state.form_data)
        lxc = LXCManifest.create(form=form_data)
        state.reset()
        return [
            LaunchApplianceDialog.create_in_background(lxc),
            components.Dialog.close(LaunchApplianceDialog.dialog_id),
            components.ProgressPanels.reset(LaunchApplianceDialog.progress_id),
            rx.toast.info(message=f"Creating LXC {lxc.name}"),
            # TODO: Clear cache for table once table is created.
        ]

    @staticmethod
    @rx.event
    async def cancel(state: LaunchLXCState) -> FrontendEvents:
        """Cancel the appliance creation process and reset the dialog state."""
        state.reset()
        return [
            components.Dialog.close(LaunchApplianceDialog.dialog_id),
            components.ProgressPanels.reset(LaunchApplianceDialog.progress_id),
        ]

    @staticmethod
    @rx.event(background=True)
    async def create_in_background(_: rx.State, lxc: LXCManifest) -> FrontendEvents:
        """Launch an LXC container in the background and notify when it is running."""
        await rx.run_in_thread(lambda: ProxmoxCompute().launch_lxc(lxc=lxc))
        return [
            rx.toast.success(message=f"LXC {lxc.name} running!"),
            # TODO: Clear cache for table once table is created.
        ]

    dialog_id: Final = "launch-appliance-dialog"
    progress_id: Final = "launch-appliance-progress-panels"

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
                    "Review & Verify",
                    ReviewPanel(),
                    validate=cls.create_lxc,
                ),
                cancel_button=components.Buttons.Secondary("Cancel", on_click=cls.cancel),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )
