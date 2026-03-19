"""OrbitLab LXC Dialogs."""

from typing import Final

import reflex as rx

from orbitlab.data_types import ComputeStatus, FrontendEvents
from orbitlab.manifest.compute_instances.lxc import LXCManifest
from orbitlab.web import components
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.utilities import EventGroup, get_worker

from .models import CreateLXCForm
from .progress_panels import GeneralConfigurationPanel, ReviewPanel
from .states import LaunchLXCState, LXCInstancesTableState


class LaunchApplianceDialog(EventGroup):
    """Dialog for launching LXC appliances."""

    @staticmethod
    @rx.event
    async def open(state: LaunchLXCState) -> FrontendEvents:
        """Set the default node and open the dialog."""
        state.reset()
        state.node = await state.get_var_value(ClusterDefaults.proxmox_node)
        return components.Dialog.open(LaunchApplianceDialog.dialog_id)

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
        manifest = LXCManifest.create(form_data=CreateLXCForm.model_validate(state.form_data))
        worker = get_worker()
        error = await worker.create_workflow(
            name="lxc.create",
            version="v1",
            payload={"manifest": manifest.name},
        )
        if error:
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Launching {manifest.name}..."),
            LaunchApplianceDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: LaunchLXCState) -> FrontendEvents:
        """Cancel the appliance creation process and reset the dialog state."""
        state.reset()
        return [
            components.Dialog.close(LaunchApplianceDialog.dialog_id),
            components.ProgressPanels.reset(LaunchApplianceDialog.progress_id),
        ]

    dialog_id: Final = "launch-appliance-dialog"
    progress_id: Final = "launch-appliance-progress-panels"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            "Create LXC Instance",
            components.ProgressPanels(
                components.ProgressPanels.Step(
                    "General Configuration",
                    GeneralConfigurationPanel(),
                    validate=cls.validate_general,
                ),
                components.ProgressPanels.Step(
                    "Review & Verify",
                    ReviewPanel(),
                    validate=cls.create_lxc,
                ),
                cancel_button=components.Buttons.Secondary("Cancel", on_click=cls.close),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )


class TerminateLXCInstanceDialog(EventGroup):
    """Terminate a running LXC instance Dialog."""

    @staticmethod
    @rx.event
    async def confirm(state: LXCInstancesTableState, instance_id: str) -> FrontendEvents:
        """Set the instance ID to terminate and open the dialog."""
        state.instance_to_terminate = instance_id
        return components.Dialog.open(TerminateLXCInstanceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def terminate(state: LXCInstancesTableState) -> None:
        """Update the status of an LXC container and trigger backend and frontend updates."""
        worker = get_worker()
        error = await worker.create_workflow(
            name="lxc.state-change",
            version="v1",
            payload={"manifest": state.instance_to_terminate, "desired_status": ComputeStatus.TERMINATE},
        )
        if error:
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Terminating {state.instance_to_terminate}..."),
            TerminateLXCInstanceDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: LXCInstancesTableState) -> FrontendEvents:
        """Cancel terminating the instance."""
        state.instance_to_terminate = ""
        return components.Dialog.close(TerminateLXCInstanceDialog.dialog_id)

    dialog_id: Final = "terminate-lxc-instance-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            "Terminate LXC Instance",
            rx.el.div(
                rx.text(
                    "You are about to terminate ",
                    rx.el.span(LXCInstancesTableState.instance_to_terminate, class_name="font-bold"),
                    ". This will delete all attached disks.",
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            rx.el.div(
                components.Buttons.Secondary("Cancel", on_click=cls.close),
                components.Buttons.Primary("Confirm", on_click=cls.terminate),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )
