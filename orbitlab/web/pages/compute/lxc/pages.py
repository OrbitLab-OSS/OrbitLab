"""OrbitLab LXC Pages."""

import reflex as rx

from orbitlab.web.components import Buttons, Dialog, PageHeader
from orbitlab.web.pages.compute.layout import compute_page

from .dialogs import CreateApplianceDialog, DownloadApplianceDialog
from .tables import BaseApplianceTable


@rx.page("/compute/lxc/appliances")
@compute_page
def appliances_page() -> rx.Component:
    """Render the LXC appliances management page."""
    return rx.el.div(
        PageHeader(
            "LXC Appliance Management",
            Buttons.Secondary(
                "Create Custom Appliance",
                icon="pen",
                on_click=Dialog.open(CreateApplianceDialog.dialog_id),
            ),
            Buttons.Primary(
                "Download Base Appliance",
                icon="cloud-download",
                on_click=Dialog.open(DownloadApplianceDialog.dialog_id),
            ),
        ),
        BaseApplianceTable(),
        DownloadApplianceDialog(),
        CreateApplianceDialog(),
        class_name="w-full h-full flex flex-col",
    )
