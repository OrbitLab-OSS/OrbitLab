"""OrbitLab Compute Management Dashboard."""

import reflex as rx

from orbitlab.web import components

from .layout import compute_page
from .lxc.running.dialogs import LaunchApplianceDialog


@rx.page("/compute")
@compute_page
def compute_dashboard() -> rx.Component:
    """Proxmox Nodes Page."""
    return rx.el.div(
        components.PageHeader(
            "Compute Management",
            components.Buttons.Primary("Create LXC", on_click=components.Dialog.open(LaunchApplianceDialog.dialog_id)),
        ),
        LaunchApplianceDialog(),
        class_name="w-full h-full",
    )
