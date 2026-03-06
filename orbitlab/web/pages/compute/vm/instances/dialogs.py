"""OrbitLab LXC Dialogs."""

from typing import Final

import reflex as rx

from orbitlab.data_types import ComputeStatus, FrontendEvents
from orbitlab.manifest.compute_instances.vm import VMManifest
from orbitlab.web import components
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.utilities import EventGroup, get_worker

from .models import CreateVMForm
from .progress_panels import GeneralConfigurationPanel, ReviewPanel
from .states import LaunchVMDialogState, VMInstancesTableState


class LaunchVMDialog(EventGroup):
    """Dialog for launching VMs from images."""

    @staticmethod
    @rx.event
    async def validate_general(state: LaunchVMDialogState, form: dict) -> FrontendEvents:
        """Update the form data with new values and proceed to the next step in the progress panel."""
        form["memory"] = int(form["memory"])
        form["sockets"] = int(form["sockets"])
        form["cores"] = int(form["cores"])
        form["disk_size"] = int(form["disk_size"])
        state.form_data.update(form)
        return components.ProgressPanels.next(LaunchVMDialog.progress_id)

    @staticmethod
    @rx.event
    async def validate_network(state: LaunchVMDialogState, form: dict) -> FrontendEvents:
        """Validate network configuration and proceed to the next step in the progress panel."""
        state.form_data.update(form)
        return components.ProgressPanels.next(LaunchVMDialog.progress_id)

    @staticmethod
    @rx.event
    async def create_vm(state: LaunchVMDialogState, form: dict) -> FrontendEvents:
        """Validate the form, create a VM manifest, reset the state, and trigger VM creation in the background."""
        state.form_data.update(form)
        manifest = VMManifest.create(form_data=CreateVMForm.model_validate(state.form_data))
        worker = get_worker()
        error = await worker.create_workflow(
            name="vm.create",
            version="v1",
            payload={"manifest": manifest.name},
        )
        if error:
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Launching {manifest.name}..."),
            LaunchVMDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: LaunchVMDialogState) -> FrontendEvents:
        """Cancel the VM creation process and reset the dialog state."""
        state.reset()
        return [
            components.Dialog.close(LaunchVMDialog.dialog_id),
            components.ProgressPanels.reset(LaunchVMDialog.progress_id),
        ]

    @staticmethod
    @rx.event
    async def set_defaults(state: LaunchVMDialogState) -> None:
        """Set default values in the form data when the dialog is opened."""
        state.form_data["node"] = await state.get_var_value(ClusterDefaults.proxmox_node)

    dialog_id: Final = "launch-vm-instance-dialog"
    progress_id: Final = "launch-vm-instance-progress-panels"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            "Launch VM",
            components.ProgressPanels(
                components.ProgressPanels.Step(
                    "General Configuration",
                    GeneralConfigurationPanel(),
                    validate=cls.validate_general,
                ),
                components.ProgressPanels.Step(
                    "Review & Verify",
                    ReviewPanel(),
                    validate=cls.create_vm,
                ),
                cancel_button=components.Buttons.Secondary("Cancel", on_click=cls.close),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            on_open=cls.set_defaults,
            class_name="max-w-[75vw] w-fit",
        )


class TerminateVMInstanceDialog(EventGroup):
    """Terminate a running VM instance Dialog."""

    @staticmethod
    @rx.event
    async def confirm(state: VMInstancesTableState, instance_id: str) -> FrontendEvents:
        """Set the instance ID to terminate and open the dialog."""
        state.instance_to_terminate = instance_id
        return components.Dialog.open(TerminateVMInstanceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def terminate(state: VMInstancesTableState) -> None:
        """Update the status of an LXC container and trigger backend and frontend updates."""
        worker = get_worker()
        error = await worker.create_workflow(
            name="vm.state-change",
            version="v1",
            payload={"manifest": state.instance_to_terminate, "desired_status": ComputeStatus.TERMINATE},
        )
        if error:
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Terminating {state.instance_to_terminate}..."),
            TerminateVMInstanceDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: VMInstancesTableState) -> FrontendEvents:
        """Cancel terminating the instance."""
        state.instance_to_terminate = ""
        return components.Dialog.close(TerminateVMInstanceDialog.dialog_id)

    dialog_id: Final = "terminate-lxc-instance-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return components.Dialog(
            "Terminate LXC Instance",
            rx.el.div(
                rx.text(
                    "You are about to terminate ",
                    rx.el.span(VMInstancesTableState.instance_to_terminate, class_name="font-bold"),
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
            class_name="max-w-[40vw] w-fit",
        )
