"""Dashboard module for displaying and managing Proxmox nodes."""

import reflex as rx

from orbitlab.web import tailwind
from orbitlab.web.components.dialogs import ConfirmUpdateInfrastructureDialog
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.layout import orbitlab_page

from .dialogs import CreateDataCoreDialog, DeleteDataCoreDialog
from .tables import DataCoreClustersTable


@rx.page("/datacore")
@orbitlab_page
def datacore_dashboard() -> rx.Component:
    """DataCore Dashboard Page."""
    return rx.el.div(
        tailwind.PageHeader(
            "DataCores",
            tailwind.Buttons.Primary(
                "Create DataCore",
                icon="plus",
                on_click=CreateDataCoreDialog.open,
            ),
        ),
        DataCoreClustersTable(
            name="DataCores",
            headers=["ID", "Name", "Replicas", "Status", "Capacity", "Cores", "Memory", ""],
            data=OrbitLabState.datacores,
            refresh=OrbitLabState.cache_clear("datacores"),
        ),
        CreateDataCoreDialog(),
        DeleteDataCoreDialog(),
        ConfirmUpdateInfrastructureDialog(),
        class_name="w-full h-full",
    )
