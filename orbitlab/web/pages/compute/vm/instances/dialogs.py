"""OrbitLab LXC Dialogs."""

from typing import Final

import reflex as rx

from orbitlab.data_types import ProxmoxComputeStatus, FrontendEvents
from orbitlab.redis.clients import ImagesClient, SecretsClient, SectorClient, VMClient
from orbitlab.redis.models import VMInstanceConfig
from orbitlab.web import tailwind
from orbitlab.web.utilities import EventGroup, create_workflow

from .progress_panels import GeneralConfigurationPanel, ReviewPanel
from .states import LaunchVMDialogState, VMInstancesTableState


class LaunchVMDialog(EventGroup):
    """Dialog for launching VMs from images."""

    @staticmethod
    @rx.event
    async def update_form_data(state: LaunchVMDialogState, form: dict) -> FrontendEvents:
        """Update the form data with new values and proceed to the next step in the progress panel."""
        state.form_data.update(form)
        return tailwind.ProgressPanels.next(LaunchVMDialog.progress_id)

    @staticmethod
    @rx.event
    async def create_vm(state: LaunchVMDialogState, form: dict) -> FrontendEvents:
        """Validate the form, create a VM manifest, reset the state, and trigger VM creation in the background."""
        state.form_data.update(form)
        client = VMClient()
        
        instance_id = await client.generate_instance_id()
        sector = await SectorClient().get(id=state.form_data["sector"])
        volume_id = await ImagesClient().get_volume_id(id=state.form_data["image"])
        
        await SecretsClient().create_vm_password(vm_id=instance_id, password=state.form_data.get("password", ""))
        await client.set_instance(
            config=VMInstanceConfig(
                id=instance_id,
                image_id=state.form_data["image"],
                volume_id=volume_id,
                storage=state.form_data["storage"],
                sector=sector.config.id,
                sector_name=sector.config.alias,
                disk_size=int(state.form_data["disk_size"]),
                memory=int(state.form_data["memory"]),
                cores=int(state.form_data["cores"]),
                sockets=int(state.form_data["sockets"]),
                node=state.form_data["node"],
            ),
        )
        if error := await create_workflow(name="vm.create", version="v1", payload={"id": instance_id}):
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Launching {instance_id}..."),
            LaunchVMDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: LaunchVMDialogState) -> FrontendEvents:
        """Cancel the VM creation process and reset the dialog state."""
        state.reset()
        return [
            tailwind.Dialog.close(LaunchVMDialog.dialog_id),
            tailwind.ProgressPanels.reset(LaunchVMDialog.progress_id),
        ]

    dialog_id: Final = "launch-vm-instance-dialog"
    progress_id: Final = "launch-vm-instance-progress-panels"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
            "Launch VM",
            tailwind.ProgressPanels(
                tailwind.ProgressPanels.Step(
                    "General Configuration",
                    GeneralConfigurationPanel(),
                    validate=cls.update_form_data,
                ),
                tailwind.ProgressPanels.Step(
                    "Review & Verify",
                    ReviewPanel(),
                    validate=cls.create_vm,
                ),
                cancel_button=tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )


class TerminateVMInstanceDialog(EventGroup):
    """Terminate a running VM instance Dialog."""

    @staticmethod
    @rx.event
    async def confirm(state: VMInstancesTableState, instance_id: str) -> FrontendEvents:
        """Set the instance ID to terminate and open the dialog."""
        state.instance_to_terminate = instance_id
        return tailwind.Dialog.open(TerminateVMInstanceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def terminate(state: VMInstancesTableState) -> None:
        """Update the status of an LXC container and trigger backend and frontend updates."""
        payload = {"id": state.instance_to_terminate, "desired_status": ProxmoxComputeStatus.TERMINATE}
        if error := await create_workflow(name="vm.state-change", version="v1", payload=payload):
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
        return tailwind.Dialog.close(TerminateVMInstanceDialog.dialog_id)

    dialog_id: Final = "terminate-lxc-instance-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
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
                tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                tailwind.Buttons.Primary("Confirm", on_click=cls.terminate),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )
