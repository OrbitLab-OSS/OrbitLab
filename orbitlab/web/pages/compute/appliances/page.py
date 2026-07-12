"""OrbitLab LXC Pages."""

import reflex as rx

from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.layout import orbitlab_page

from .dialogs import CustomApplianceDialog, Dialogs, DownloadApplianceDialog, PullOCIApplianceDialog
from .tables import BaseApplianceTable, CustomApplianceTable


@rx.page("/compute/appliances")
@orbitlab_page
def appliances_page() -> rx.Component:
    """Render the LXC appliances management page."""
    return rx.fragment(
        tailwind.PageHeader(
            "LXC Appliance Management",
            tailwind.Buttons.Secondary(
                "Pull OCI Container",
                icon="arrow-down-to-line",
                on_click=PullOCIApplianceDialog.open,
            ),
            tailwind.Buttons.Secondary(
                "Create Custom Appliance",
                icon="pen",
                on_click=lambda: CustomApplianceDialog.start_appliance_creation(""),
            ),
            tailwind.Buttons.Primary(
                "Download Base Appliance",
                icon="cloud-download",
                on_click=DownloadApplianceDialog.open,
            ),
        ),
        BaseApplianceTable(
            name="Base Appliances",
            headers=["ID", "Name", "Node", "Storage", "Date Downloaded", ""],
            data=OrbitLabState.base_appliances, # pyright: ignore[reportArgumentType]
            refresh=OrbitLabState.cache_clear("base_appliances")
        ),
        CustomApplianceTable(
            name="Custom Appliances",
            headers=["ID", "Name", "Workflow Status", "Workflow Steps", "Created", "Last Executed", ""],
            data=OrbitLabState.custom_appliances, # pyright: ignore[reportArgumentType]
            refresh=OrbitLabState.cache_clear("custom_appliances")
        ),
        Dialogs(),
    )
