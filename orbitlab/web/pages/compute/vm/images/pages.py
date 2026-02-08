"""OrbitLab VM Image Pages."""

import reflex as rx

from orbitlab.web.components import Buttons, PageHeader
from orbitlab.web.pages.compute.layout import compute_page

from .dialogs import CustomImageDialog
from .tables import BaseImagesTable, CustomImagesTable


@rx.page("/compute/vm/images")
@compute_page
def images_page() -> rx.Component:
    """Render the VM Images page."""
    return rx.el.div(
        PageHeader(
            "VM Image Management",
            Buttons.Secondary(
                "Create Custom Image",
                icon="pen",
                on_click=CustomImageDialog.start_image_creation(""),
            ),
            Buttons.Primary(
                "Download Base Image",
                icon="cloud-download",
            ),
        ),
        BaseImagesTable(),
        CustomImagesTable(),
        CustomImageDialog(),
        class_name="w-full h-full flex flex-col",
    )
