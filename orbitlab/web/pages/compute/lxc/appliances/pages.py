"""OrbitLab LXC Pages."""

import reflex as rx

from orbitlab.web.tailwind import Buttons, Dialog, PageHeader
from orbitlab.web.layout import orbitlab_page

from .dialogs import CustomApplianceDialog, DeleteApplianceDialog, DownloadApplianceDialog
from .tables import BaseApplianceTable, CustomApplianceTable


@rx.page("/compute/lxc/appliances")
@orbitlab_page
def appliances_page() -> rx.Component:
    """Render the LXC appliances management page."""
    return rx.el.div(
        PageHeader(
            "LXC Appliance Management",
            Buttons.Secondary(
                "Create Custom Appliance",
                icon="pen",
                on_click=CustomApplianceDialog.start_appliance_creation(""),
            ),
            Buttons.Primary(
                "Download Base Appliance",
                icon="cloud-download",
                on_click=Dialog.open(DownloadApplianceDialog.dialog_id),
            ),
        ),
        BaseApplianceTable(),
        CustomApplianceTable(),
        DownloadApplianceDialog(),
        DeleteApplianceDialog(),
        class_name="w-full h-full flex flex-col",
    )
