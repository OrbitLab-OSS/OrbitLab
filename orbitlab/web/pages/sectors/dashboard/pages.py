"""OrbitLab Networks Dashboard Pages."""

import reflex as rx

from orbitlab.web import components
from orbitlab.web.pages.sectors.layout import sectors_page

from .dialogs import CreateSectorDialog
from .tables import SectorsTable, StatusTable


@rx.page("/sectors")
@sectors_page
def sectors_dashboard() -> rx.Component:
    """Render the networks management dashboard page."""
    return rx.el.div(
        components.PageHeader(
            "Sector Management",
            components.Buttons.Primary(
                "Create Sector",
                on_click=components.Dialog.open(CreateSectorDialog.dialog_id),
            ),
        ),
        StatusTable(),
        SectorsTable(),
        CreateSectorDialog(),
    )
