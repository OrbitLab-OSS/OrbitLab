"""OrbitLab LXC Dialogs."""

from typing import Final

import reflex as rx

from orbitlab.clients.proxmox.compute.client import ProxmoxCompute
from orbitlab.data_types import FrontendEvents
from orbitlab.manifest.compute_instances.vm import VMManifest
from orbitlab.web import components
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.utilities import EventGroup

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
        form_data = CreateVMForm.model_validate(state.form_data)
        vm = VMManifest.create(form_data=form_data)
        state.reset()
        return [
            LaunchVMDialog.create_in_background(vm),
            components.Dialog.close(LaunchVMDialog.dialog_id),
            components.ProgressPanels.reset(LaunchVMDialog.progress_id),
            rx.toast.info(message=f"Creating VM {vm.name}..."),
            VMInstancesTableState.cache_clear("running"),
        ]

    @staticmethod
    @rx.event
    async def cancel(state: LaunchVMDialogState) -> FrontendEvents:
        """Cancel the VM creation process and reset the dialog state."""
        state.reset()
        return [
            components.Dialog.close(LaunchVMDialog.dialog_id),
            components.ProgressPanels.reset(LaunchVMDialog.progress_id),
        ]

    @staticmethod
    @rx.event(background=True)
    async def create_in_background(_: rx.State, vm_manifest: VMManifest) -> FrontendEvents:
        """Launch a VM in the background and notify when it is running."""
        await rx.run_in_thread(lambda: ProxmoxCompute().launch_vm(vm_manifest=vm_manifest))
        return [
            rx.toast.success(message=f"VM {vm_manifest.name} running!"),
            VMInstancesTableState.cache_clear("running"),
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
                cancel_button=components.Buttons.Secondary("Cancel", on_click=cls.cancel),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            on_open=cls.set_defaults,
            class_name="max-w-[75vw] w-fit",
        )
