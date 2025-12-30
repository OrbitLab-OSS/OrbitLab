"""OrbitLab Networks Dashboard Pages."""


import reflex as rx

from orbitlab.web import components
from orbitlab.web.pages.sectors.layout import sectors_page

from .tables import StatusTable


@rx.page("/sectors/appliances")
@sectors_page
def sectors_appliances() -> rx.Component:
    """Render the sector appliances management dashboard page."""
    return rx.el.div(
        components.PageHeader(
            "Sector Appliance Management",
        ),
        StatusTable(),
    )
