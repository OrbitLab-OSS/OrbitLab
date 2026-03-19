"""OrbitLab Networks Dashboard Pages."""

import reflex as rx

from orbitlab.web import components
from orbitlab.web.layout import orbitlab_page

from .dialogs import CreateSectorDialog
from .tables import SectorsTable


@rx.page("/sectors")
@orbitlab_page
def sectors_dashboard() -> rx.Component:
    """Render the networks management dashboard page."""
    return rx.el.div(
        components.PageHeader(
            "Sector Management",
            components.Buttons.Primary(
                "Create Sector",
                icon="plus",
                on_click=components.Dialog.open(CreateSectorDialog.dialog_id),
            ),
        ),
        SectorsTable(),
        CreateSectorDialog(),
    )
