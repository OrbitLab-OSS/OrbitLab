"""Running LXCs Management Pages."""

import reflex as rx

from orbitlab.web import tailwind
from orbitlab.web.layout import orbitlab_page

from .dialogs import LaunchLXCInstanceDialog
from .tables import LXCInstancesTable


@rx.page("/compute/lxc/instances")
@orbitlab_page
def lxc_instances() -> rx.Component:
    """Render the Running LXCs Management page."""
    return rx.el.div(
        tailwind.PageHeader(
            "LXC Instances",
            tailwind.Buttons.Primary("Create LXC", on_click=tailwind.Dialog.open(LaunchLXCInstanceDialog.dialog_id)),
        ),
        LaunchLXCInstanceDialog(),
        LXCInstancesTable(),
        class_name="w-full h-full",
    )
