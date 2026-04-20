"""Dashboard module for displaying and managing Proxmox nodes."""

import reflex as rx

from orbitlab.web import tailwind

from .dialogs import CreateDockFSDialog, DeleteDockFSDialog
from orbitlab.web.layout import orbitlab_page

from .tables import DockFSTable


@rx.page("/dock-fs")
@orbitlab_page
def dockfs_dashboard() -> rx.Component:
    """DockFS Dashboard Page."""
    return rx.el.div(
        tailwind.PageHeader(
            "DockFS Clusters",
            tailwind.Buttons.Primary("Create DockFS", icon="plus", on_click=tailwind.Dialog.open(CreateDockFSDialog.dialog_id)),
        ),
        DockFSTable(),
        CreateDockFSDialog(),
        DeleteDockFSDialog(),
        class_name="w-full h-full",
    )
