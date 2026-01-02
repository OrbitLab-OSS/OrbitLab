"""OrbitLab LXC Dialogs."""

from typing import Final

import reflex as rx

from orbitlab.clients.proxmox.compute.client import ProxmoxCompute
from orbitlab.data_types import FrontendEvents
from orbitlab.manifest.lxc import LXCManifest
from orbitlab.web import components
from orbitlab.web.utilities import EventGroup

from .models import CreateLXCForm
from .progress_panels import GeneralConfigurationPanel, NetworkConfigurationPanel, ReviewPanel
from .states import LaunchLXCState, LXCsState


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
            LXCsState.cache_clear("running"),
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
            LXCsState.cache_clear("running"),
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
