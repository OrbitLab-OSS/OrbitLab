"""OrbitLab VM Image Pages."""

import reflex as rx

from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.layout import orbitlab_page

from .dialogs import CustomImageDialog, Dialogs, DownloadImageDialog
from .tables import BaseImagesTable, CustomImagesTable


@rx.page("/compute/images")
@orbitlab_page
def images_page() -> rx.Component:
    """Render the VM Images page."""
    return rx.el.div(
        tailwind.PageHeader(
            "VM Image Management",
            tailwind.Buttons.Secondary(
                "Create Custom Image",
                icon="pen",
                on_click=CustomImageDialog.start_image_creation(""),
            ),
            tailwind.Buttons.Primary(
                "Download Base Image",
                icon="cloud-download",
                on_click=DownloadImageDialog.open,
            ),
        ),
        BaseImagesTable(
            name="Base Images",
            headers=["Image ID", "OS", "Node", "Storage", "Download Date", ""],
            data=OrbitLabState.base_images,
            refresh=OrbitLabState.cache_clear("base_images")
        ),
        CustomImagesTable(
            name="Custom Images",
            headers=["ID", "Name", "Base Image", "Workflow Status", "Workflow Steps", "Date Created", ""],
            data=OrbitLabState.custom_images,
            refresh=OrbitLabState.cache_clear("custom_images")
        ),
        Dialogs(),
        class_name="w-full h-full flex flex-col",
    )
