from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.web import tailwind
from orbitlab.web.global_state import InfrastructureManagementState
from orbitlab.web.utilities import EventGroup, create_workflow


class ConfirmUpdateInfrastructureDialog(EventGroup):

    @staticmethod
    @rx.event
    async def open(_: rx.State) -> FrontendEvents:
        """Open the dialog."""
        return tailwind.Dialog.open(ConfirmUpdateInfrastructureDialog.dialog_id)
    
    @staticmethod
    @rx.event
    async def update_infra_appliances(_: rx.State) -> FrontendEvents:
        """Open the dialog."""
        if error := await create_workflow(name="infrastructure.download", version="v1", payload={}):
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Updating OrbitLab Infrastructure Appliances..."),
            tailwind.Dialog.close(ConfirmUpdateInfrastructureDialog.dialog_id),
        ]
    
    dialog_id: Final = "confirm-update-infrastructure-appliances-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
            "Appliance Update Required",
            rx.el.div(
                rx.el.p((
                    "Before updating any running infrastrcuture, the latest appliances must be downloaded to Proxmox. "
                    "To begin updating the stored appliances, click Update."
                )),
            ),
            rx.el.div(
                tailwind.Buttons.Secondary("Cancel", on_click=tailwind.Dialog.close(ConfirmUpdateInfrastructureDialog.dialog_id)),
                tailwind.Buttons.Primary("Update", on_click=cls.update_infra_appliances),
                class_name="w-full flex space-x-3 items-center justify-end",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-fit",
        )


class UpgradeETCDDialog(EventGroup):
    """Upgrade the ETCD cluster."""

    @staticmethod
    @rx.event
    async def open(_: rx.State) -> FrontendEvents:
        return tailwind.Dialog.open(UpgradeETCDDialog.dialog_id)

    @staticmethod
    @rx.event
    async def upgrade(_: rx.State) -> FrontendEvents:
        """Delete the DataCore cluster."""
        if error := await create_workflow(name="etcd.upgrade", version="v1", payload={}):
            return rx.toast.error(error)
        return [
            tailwind.Dialog.close(UpgradeETCDDialog.dialog_id),
            rx.toast.info("Upgading ETCD cluster..."),
        ]

    @staticmethod
    @rx.event
    async def close(_: rx.State) -> FrontendEvents:
        return tailwind.Dialog.close(UpgradeETCDDialog.dialog_id)

    dialog_id: Final = "confirm-upgrade-etcd-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return dialog component."""
        return tailwind.Dialog(
            "Upgrade ETCD",
            rx.el.div(
                rx.text(
                    (
                        "You are about to upgrade the ETCD cluster from "
                        f"v{InfrastructureManagementState.etcd_version} to v{InfrastructureManagementState.current_version}. "
                        "This process will upgrade one member node at a time by creating a replacement node with the new "
                        "appliance version and then removing its predecessor."
                    )
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            rx.el.div(
                tailwind.Buttons.Secondary("Cancel", on_click=UpgradeETCDDialog.close),
                tailwind.Buttons.Primary("Begin", on_click=cls.upgrade),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )
