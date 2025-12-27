"""OrbitLab Compute Management Dashboard."""

import reflex as rx

from orbitlab.web import components

from .layout import compute_page


@rx.page("/compute")
@compute_page
def compute_dashboard() -> rx.Component:
    """Proxmox Nodes Page."""
    return rx.el.div(
        components.PageHeader(
            "Compute Management",
            components.Buttons.Primary("Create LXC"),
        ),
        class_name="w-full h-full",
    )
