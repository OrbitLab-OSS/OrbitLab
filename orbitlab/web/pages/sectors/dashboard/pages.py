"""OrbitLab Networks Dashboard Pages."""

import reflex as rx

from orbitlab.web import tailwind
from orbitlab.web.layout import orbitlab_page

from .dialogs import CreateSectorDialog
from .tables import SectorsTable


@rx.page("/sectors")
@orbitlab_page
def sectors_dashboard() -> rx.Component:
    """Render the networks management dashboard page."""
    return rx.el.div(
        tailwind.PageHeader(
            "Sector Management",
            tailwind.Buttons.Primary(
                "Create Sector",
                icon="plus",
                on_click=tailwind.Dialog.open(CreateSectorDialog.dialog_id),
            ),
        ),
        SectorsTable(),
        CreateSectorDialog(),
    )
