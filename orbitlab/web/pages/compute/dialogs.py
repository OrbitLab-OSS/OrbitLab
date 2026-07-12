"""OrbitLab LXC Dialogs."""

from typing import Final, Literal

import reflex as rx

from orbitlab.data_types import InstanceType, ProxmoxComputeStatus, FrontendEvents
from orbitlab.web import tailwind
from orbitlab.redis.clients import ApplianceClient, ImagesClient, InstanceClient, SecretsClient, SectorClient
from orbitlab.redis.models import InstanceConfig
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.utilities import EventGroup, create_workflow

from .progress_panels import InstanceComputeConfigurationPanel, InstanceReviewPanel, InstanceSecurityConfigurationPanel


class LaunchComputeInstanceDialogState(rx.State):
    form_data: rx.Field[dict] = rx.field(default_factory=dict)
    

class LaunchComputeInstanceDialog(EventGroup):

    @staticmethod
    @rx.event
    async def open(state: LaunchComputeInstanceDialogState, instance_type: InstanceType) -> None:
        state.form_data["type"] = instance_type
        return tailwind.Dialog.open(LaunchComputeInstanceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def update_form_data(state: LaunchComputeInstanceDialogState, form: dict) -> FrontendEvents:
        state.form_data.update(form)
        return tailwind.ProgressPanels.next(LaunchComputeInstanceDialog.progress_id)

    @staticmethod
    @rx.event
    async def validate_password(_: rx.State, form: dict) -> FrontendEvents:
        if not form["password"] == form["password_confirmation"]:
            return rx.toast.error("Passwords must match.")
        return LaunchComputeInstanceDialog.update_form_data(form)

    @staticmethod
    @rx.event
    async def create_instance(state: LaunchComputeInstanceDialogState, form: dict) -> FrontendEvents:
        client = InstanceClient()
        
        state.form_data.update(form)
        state.form_data["id"] = await client.generate_instance_id()
        state.form_data["sector_name"] = (await SectorClient().get(id=state.form_data["sector"])).config.alias
        state.form_data["nfs"] = bool(state.form_data.get("nfs") == "on")
        
        if state.form_data["type"] == "lxc":
            state.form_data["volume_id"] = await ApplianceClient().get_volume_id(id=state.form_data["base_id"])            
        else:
            state.form_data["volume_id"] = await ImagesClient().get_volume_id(id=state.form_data["base_id"])
        
        config = InstanceConfig.model_validate(state.form_data)
        await client.set_instance(config=config)
        await SecretsClient().create_instance_password(instance_id=config.id, password=state.form_data.get("password", ""))
        
        if error := await create_workflow(name="instance.create", version="v1", payload={"id": config.id}):
            return rx.toast.error(error)
        return [
            LaunchComputeInstanceDialog.close,
            rx.toast.info(f"Launching {config.id}..."),
            OrbitLabState.cache_clear("instances"),
        ]

    @staticmethod
    @rx.event
    async def close(state: LaunchComputeInstanceDialogState) -> FrontendEvents:
        """Cancel the appliance creation process and reset the dialog state."""
        state.reset()
        return [
            tailwind.Dialog.close(LaunchComputeInstanceDialog.dialog_id),
            tailwind.ProgressPanels.reset(LaunchComputeInstanceDialog.progress_id),
        ]

    dialog_id: Final = "launch-appliance-dialog"
    progress_id: Final = "launch-appliance-progress-panels"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
            "Create LXC Instance",
            tailwind.ProgressPanels(
                tailwind.ProgressPanels.Step(
                    "Compute Configuration",
                    InstanceComputeConfigurationPanel(instance_type=LaunchComputeInstanceDialogState.form_data["type"].to(str)),
                    validate=cls.update_form_data,
                ),
                tailwind.ProgressPanels.Step(
                    "Security Configuration",
                    InstanceSecurityConfigurationPanel(),
                    validate=cls.validate_password,
                ),
                tailwind.ProgressPanels.Step(
                    "Review & Verify",
                    InstanceReviewPanel(form_data=LaunchComputeInstanceDialogState.form_data),
                    validate=cls.create_instance,
                ),
                cancel_button=tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-fit",
        )


class TerminateInstanceState(rx.State):
    instance_type: rx.Field[Literal["lxc", "qemu"]] = rx.field(default="lxc")
    instance_id: rx.Field[str] = rx.field(default="")


class TerminateInstanceDialog(EventGroup):

    @staticmethod
    @rx.event
    async def confirm(state: TerminateInstanceState, instance_id: str, instance_type: InstanceType) -> FrontendEvents:
        """Set the instance ID to terminate and open the dialog."""
        state.instance_type = instance_type
        state.instance_id = instance_id
        return tailwind.Dialog.open(TerminateInstanceDialog.dialog_id)

    @staticmethod
    @rx.event
    async def terminate(state: TerminateInstanceState) -> None:
        """Update the status of an LXC container and trigger backend and frontend updates."""
        payload = {"id": state.instance_id, "instance_type": state.instance_type, "desired_status": ProxmoxComputeStatus.TERMINATE}
        if error := await create_workflow(name="instance.state-change", version="v1", payload=payload):
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Terminating {state.instance_id}..."),
            TerminateInstanceDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: TerminateInstanceState) -> FrontendEvents:
        """Cancel terminating the instance."""
        state.instance_id = ""
        return tailwind.Dialog.close(TerminateInstanceDialog.dialog_id)

    dialog_id: Final = "terminate-instance-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
            f"Terminate {TerminateInstanceState.instance_type.to(str).upper()} Instance",
            rx.el.div(
                rx.text(
                    "You are about to terminate ",
                    rx.el.span(TerminateInstanceState.instance_id, class_name="font-bold"),
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
