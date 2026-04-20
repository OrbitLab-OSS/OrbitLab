"""Compute Autoscaling Pages."""

import reflex as rx

from orbitlab.web import tailwind
from orbitlab.web.layout import orbitlab_page

from .dialogs import CreatePoolDialog

@rx.page("/compute/autoscaling")
@orbitlab_page
def autoscaling_page() -> rx.Component:
    return rx.el.div(
        tailwind.PageHeader(
            "Autoscaling Pools",
            tailwind.Buttons.Primary("Create Pool", icon="plus", on_click=CreatePoolDialog.open),
        ),
        CreatePoolDialog(),
        class_name="w-full h-full",
    )
