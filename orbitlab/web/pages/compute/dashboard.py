"""OrbitLab Compute Management Dashboard."""

import reflex as rx

from orbitlab.web.components import PageHeader

from .layout import compute_page


@rx.page("/compute")
@compute_page
def compute_dashboard() -> rx.Component:
    """Proxmox Nodes Page."""
    return rx.el.div(
        PageHeader(
            "Compute Management",
        ),
        class_name="w-full h-full",
    )
