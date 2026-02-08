"""Running LXCs Management Pages."""

import reflex as rx

from orbitlab.web import components
from orbitlab.web.pages.compute.layout import compute_page

from .dialogs import LaunchApplianceDialog
from .tables import LXCInstancesTable


@rx.page("/compute/lxc/instances")
@compute_page
def lxc_instances() -> rx.Component:
    """Render the Running LXCs Management page."""
    return rx.el.div(
        components.PageHeader(
            "LXC Instances",
            components.Buttons.Primary("Create LXC", on_click=components.Dialog.open(LaunchApplianceDialog.dialog_id)),
        ),
        LaunchApplianceDialog(),
        LXCInstancesTable(),
        class_name="w-full h-full",
    )
