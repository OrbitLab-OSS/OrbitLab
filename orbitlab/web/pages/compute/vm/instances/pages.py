"""VM Instance Management Pages."""

import reflex as rx

from orbitlab.web import components
from orbitlab.web.pages.compute.layout import compute_page

from .dialogs import LaunchVMDialog
from .tables import VMInstancesTable


@rx.page("/compute/vm/instances")
@compute_page
def vm_instances() -> rx.Component:
    """Render the VM Instances management page."""
    return rx.el.div(
        components.PageHeader(
            "VM Instances",
            components.Buttons.Primary("Create VM", on_click=components.Dialog.open(LaunchVMDialog.dialog_id)),
        ),
        VMInstancesTable(),
        LaunchVMDialog(),
        class_name="w-full h-full",
    )
