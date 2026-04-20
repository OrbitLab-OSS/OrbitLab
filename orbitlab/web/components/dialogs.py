from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.web import tailwind
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
