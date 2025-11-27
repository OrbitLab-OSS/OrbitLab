"""OrbitLab LXC Dialogs."""

from typing import TYPE_CHECKING, Final

import reflex as rx

from orbitlab.clients.proxmox.client import Proxmox
from orbitlab.clients.proxmox.models import ApplianceInfo
from orbitlab.data_types import ApplianceType, FrontendEvents, ManifestKind
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.appliances import BaseApplianceManifest
from orbitlab.web.components import Buttons, Dialog, GridList, Input, OrbitLabLogo, ProgressPanels, RadioGroup, Select
from orbitlab.web.states.cluster import OrbitLabSettings
from orbitlab.web.states.utilities import EventGroup

from .models import CreateCustomApplianceForm
from .progress_panels import GeneralConfigurationPanel, ReviewPanel, WorkflowConfigurationPanel
from .states import CreateApplianceState, DownloadApplianceState

if TYPE_CHECKING:
    from orbitlab.manifest.schemas.nodes import NodeManifest


class DownloadApplianceDialog(EventGroup):
    """Dialog component for downloading appliance templates to Proxmox nodes.

    This class provides a user interface for selecting and downloading
    system or turnkey appliances to specified nodes and storage locations.
    It handles the download process, storage selection, and provides
    real-time feedback during the download operation.
    """

    @staticmethod
    @rx.event
    async def set_node(state: DownloadApplianceState, template: str, node: str) -> None:
        """Set the node for a template and update available storage options."""
        node_manifest: NodeManifest = ManifestClient().load(node, kind=ManifestKind.NODE)
        state.download_configs[template].node = node
        state.download_configs[template].available_storage = [
            store.name for store in node_manifest.spec.storage.root if "vztmpl" in store.content
        ]

    @staticmethod
    @rx.event(background=True)
    async def wait_for_download(
        state: DownloadApplianceState,
        manifest: BaseApplianceManifest,
        upid: str,
    ) -> FrontendEvents | None:
        """Wait for appliance download task to complete and update state."""
        try:
            Proxmox().wait_for_task(node=manifest.spec.node, upid=upid)
        except TimeoutError:
            return rx.toast.error(f"Downloading {manifest.name} timed out after 15 min.")
        else:
            ManifestClient().save(manifest=manifest)
            return rx.toast.success(f"Appliance {manifest.name} download complete!")
        finally:
            async with state:
                state.download_configs[manifest.name].downloading = False
                state.existing = list(ManifestClient().get_existing_by_kind(kind=ManifestKind.BASE_APPLIANCE).keys())

    @staticmethod
    @rx.event
    async def download_appliance(state: DownloadApplianceState, form: dict) -> FrontendEvents:
        """Download an appliance template to the specified node and storage."""
        template = form["template"]
        node = form["node"]
        storage = form["storage"]
        state.download_configs[template].downloading = True
        appliance = next(iter(apl for apl in state.available_system_appliances if apl.template == template))
        manifest = appliance.create_manifest(node=node, storage=storage)
        upid = Proxmox().download_appliance(node=manifest.spec.node, storage=manifest.spec.storage, appliance=appliance)
        return [
            Dialog.close(DownloadApplianceDialog.dialog_id),
            DownloadApplianceDialog.wait_for_download(manifest, upid),
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
        return GridList.Item(
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
                    Select(
                        DownloadApplianceState.available_nodes,
                        default_value=OrbitLabSettings.primary_node,
                        placeholder="Select Node",
                        name="node",
                        required=True,
                        on_change=lambda node: cls.set_node(appliance.template, node),
                    ),
                    Select(
                        DownloadApplianceState.download_configs[appliance.template].available_storage,
                        placeholder="Select Storage",
                        name="storage",
                        required=True,
                    ),
                    id=f"form-{appliance.template}",
                    on_submit=cls.download_appliance,
                ),
                rx.cond(
                    DownloadApplianceState.download_configs[appliance.template].downloading,
                    OrbitLabLogo(size=38, animated=True),
                    Buttons.Primary("Download", form=f"form-{appliance.template}"),
                ),
                class_name="flex flex-col items-center justify-center",
            ),
        )

    def __new__(cls) -> rx.Component:
        """Create and return the download appliance dialog component."""
        return Dialog(
            "Select Appliance to Download",
            rx.el.form(id=cls.form_id, on_submit=cls.download_appliance),
            rx.el.div(
                RadioGroup(
                    RadioGroup.Item(
                        "system",
                        on_change=cls.set_appliance_view("system"),
                        value=DownloadApplianceState.appliance_view,
                    ),
                    RadioGroup.Item(
                        "turnkey",
                        on_change=cls.set_appliance_view("turnkey"),
                        value=DownloadApplianceState.appliance_view,
                    ),
                ),
                Input(placeholder="Search appliances...", icon="search", on_change=cls.search_appliances),
                class_name="flex items-center justify-between mb-4 space-x-4",
            ),
            rx.scroll_area(
                rx.vstack(
                    rx.match(
                        DownloadApplianceState.appliance_view,
                        (
                            ApplianceType.TURNKEY,
                            GridList(
                                rx.foreach(
                                    DownloadApplianceState.available_turnkey_appliances,
                                    lambda apl: cls.__appliance__(apl),
                                ),
                            ),
                        ),
                        GridList(
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
                Buttons.Secondary("Close", on_click=Dialog.close(cls.dialog_id)),
                class_name="w-full flex justify-end mt-4",
            ),
            dialog_id=cls.dialog_id,
        )





class CreateApplianceDialog(EventGroup):
    """Dialog for creating custom appliances from base appliances.

    This dialog provides a multi-step interface for users to create custom appliances
    by configuring general settings, defining workflow steps, and reviewing the final
    configuration before creation.
    """

    @staticmethod
    @rx.event
    async def create_appliance_from_base(state: CreateApplianceState, base_appliance: str) -> None:
        """Initialize appliance creation from a base appliance and open the dialog."""
        state.form_data["base_appliance"] = base_appliance
        return Dialog.open(CreateApplianceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def validate_general(state: CreateApplianceState, form: dict) -> rx.event.EventCallback | rx.event.EventSpec:
        """Update the form data with new values and proceed to the next step in the progress panel."""
        name = form["name"]
        if name in ManifestClient().get_existing_by_kind(kind=ManifestKind.CUSTOM_APPLIANCE):
            return rx.toast.error(f"Appliance with name '{name}' already exists.")
        state.form_data.update(form)
        return ProgressPanels.next(CreateApplianceDialog.progress_id)

    @staticmethod
    @rx.event
    async def create_appliance(state: CreateApplianceState, form: dict) -> None:
        """Create the custom appliance with the configured settings and workflow steps."""
        state.form_data.update(form)
        form_data = CreateCustomApplianceForm.model_validate(state.form_data)
        manifest = form_data.generate_manifest()
        ManifestClient().save(manifest=manifest)
        # TODO: Add event to initiate workflow and watch progress/logs
        return CreateApplianceDialog.reset

    @staticmethod
    @rx.event
    async def reset(state: CreateApplianceState) -> list[rx.event.EventCallback]:
        """Cancel the appliance creation process and reset the dialog state."""
        state.reset()
        return [
            Dialog.close(CreateApplianceDialog.dialog_id),
            ProgressPanels.reset(CreateApplianceDialog.progress_id),
        ]

    @staticmethod
    @rx.event
    async def validate_wf_steps(state: CreateApplianceState, _: dict) -> rx.event.EventSpec | rx.event.EventCallback:
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
        return ProgressPanels.next(CreateApplianceDialog.progress_id)

    dialog_id: Final = "create-appliance-dialog"
    progress_id: Final = "create-appliance-progress-panels"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return Dialog(
            "Create Custom Appliance",
            ProgressPanels(
                ProgressPanels.Step(
                    "General Configuration",
                    GeneralConfigurationPanel(),
                    validate=cls.validate_general,
                ),
                ProgressPanels.Step(
                    "Workflow Steps",
                    WorkflowConfigurationPanel(),
                    validate=cls.validate_wf_steps,
                ),
                ProgressPanels.Step(
                    "Review & Verify",
                    ReviewPanel(),
                    validate=cls.create_appliance,
                ),
                cancel_button=Buttons.Secondary("Cancel", on_click=cls.reset),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )
