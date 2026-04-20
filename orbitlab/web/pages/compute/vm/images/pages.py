"""OrbitLab VM Image Pages."""

import reflex as rx

from orbitlab.web.tailwind import Buttons, PageHeader
from orbitlab.web.layout import orbitlab_page

from .dialogs import CustomImageDialog, DeleteImageDialog, DownloadImageDialog
from .tables import BaseImagesTable, CustomImagesTable


@rx.page("/compute/vm/images")
@orbitlab_page
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
                on_click=DownloadImageDialog.open,
            ),
        ),
        BaseImagesTable(),
        CustomImagesTable(),
        CustomImageDialog(),
        DeleteImageDialog(),
        class_name="w-full h-full flex flex-col",
    )
