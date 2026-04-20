"""OrbitLab LXC Dialogs."""

from typing import Final

import reflex as rx

from orbitlab.data_types import ProxmoxComputeStatus, FrontendEvents
from orbitlab.redis.clients import ApplianceClient, LXCClient, SecretsClient, SectorClient
from orbitlab.redis.models import LXCInstanceConfig
from orbitlab.web import tailwind
from orbitlab.web.utilities import EventGroup, create_workflow

from .progress_panels import GeneralConfigurationPanel, ReviewPanel
from .states import LaunchLXCInstanceDialogState, LXCInstancesTableState


class LaunchLXCInstanceDialog(EventGroup):
    """Dialog for launching LXC appliances."""

    @staticmethod
    @rx.event
    async def update_form_data(state: LaunchLXCInstanceDialogState, form: dict) -> FrontendEvents:
        """Update the form data with new values and proceed to the next step in the progress panel."""
        state.form_data.update(form)
        return tailwind.ProgressPanels.next(LaunchLXCInstanceDialog.progress_id)

    @staticmethod
    @rx.event
    async def create_lxc(state: LaunchLXCInstanceDialogState, form: dict) -> FrontendEvents:
        """Create the custom appliance with the configured settings and workflow steps."""
        state.form_data.update(form)
        client = LXCClient()
        
        instance_id = await client.generate_instance_id()
        sector = await SectorClient().get(id=state.form_data["sector"])
        volume_id = await ApplianceClient().get_volume_id(id=state.form_data["appliance"])
        
        await SecretsClient().create_lxc_password(lxc_id=instance_id, password=state.form_data.get("password", ""))
        await client.set_instance(
            config=LXCInstanceConfig(
                id=instance_id,
                appliance_id=state.form_data["appliance"],
                volume_id=volume_id,
                storage=state.form_data["storage"],
                sector=sector.config.id,
                sector_name=sector.config.alias,
                disk_size=int(state.form_data["disk_size"]),
                memory=int(state.form_data["memory"]),
                swap=int(state.form_data["swap"]),
                cores=int(state.form_data["cores"]),
                nfs=bool(state.form_data.get("nfs") == "on"),
                node=state.form_data["node"],
            )
        )
        if error := await create_workflow(name="lxc.create", version="v1", payload={"id": instance_id}):
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Launching {instance_id}..."),
            LaunchLXCInstanceDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: LaunchLXCInstanceDialogState) -> FrontendEvents:
        """Cancel the appliance creation process and reset the dialog state."""
        state.reset()
        return [
            tailwind.Dialog.close(LaunchLXCInstanceDialog.dialog_id),
            tailwind.ProgressPanels.reset(LaunchLXCInstanceDialog.progress_id),
        ]

    dialog_id: Final = "launch-appliance-dialog"
    progress_id: Final = "launch-appliance-progress-panels"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
            "Create LXC Instance",
            tailwind.ProgressPanels(
                tailwind.ProgressPanels.Step(
                    "General Configuration",
                    GeneralConfigurationPanel(),
                    validate=cls.update_form_data,
                ),
                tailwind.ProgressPanels.Step(
                    "Review & Verify",
                    ReviewPanel(),
                    validate=cls.create_lxc,
                ),
                cancel_button=tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
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
        return tailwind.Dialog.open(TerminateLXCInstanceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def terminate(state: LXCInstancesTableState) -> None:
        """Update the status of an LXC container and trigger backend and frontend updates."""
        payload = {"id": state.instance_to_terminate, "desired_status": ProxmoxComputeStatus.TERMINATE}
        if error := await create_workflow(name="lxc.state-change", version="v1", payload=payload):
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
        return tailwind.Dialog.close(TerminateLXCInstanceDialog.dialog_id)

    dialog_id: Final = "terminate-lxc-instance-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
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
                tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                tailwind.Buttons.Primary("Confirm", on_click=cls.terminate),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )
