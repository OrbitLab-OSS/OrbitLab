"""Running LXCs Management Pages."""

import reflex as rx

from orbitlab.web import components
from orbitlab.web.layout import orbitlab_page

from .dialogs import LaunchApplianceDialog
from .tables import LXCInstancesTable


@rx.page("/compute/lxc/instances")
@orbitlab_page
def lxc_instances() -> rx.Component:
    """Render the Running LXCs Management page."""
    return rx.el.div(
        components.PageHeader(
            "LXC Instances",
            components.Buttons.Primary("Create LXC", on_click=LaunchApplianceDialog.open),
        ),
        LaunchApplianceDialog(),
        LXCInstancesTable(),
        class_name="w-full h-full",
    )
