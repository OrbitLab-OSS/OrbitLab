"""VM Instance Management Pages."""

import reflex as rx

from orbitlab.web import tailwind
from orbitlab.web.layout import orbitlab_page

from .dialogs import LaunchVMDialog
from .tables import VMInstancesTable


@rx.page("/compute/vm/instances")
@orbitlab_page
def vm_instances() -> rx.Component:
    """Render the VM Instances management page."""
    return rx.el.div(
        tailwind.PageHeader(
            "VM Instances",
            tailwind.Buttons.Primary("Create VM", on_click=tailwind.Dialog.open(LaunchVMDialog.dialog_id)),
        ),
        VMInstancesTable(),
        LaunchVMDialog(),
        class_name="w-full h-full",
    )
