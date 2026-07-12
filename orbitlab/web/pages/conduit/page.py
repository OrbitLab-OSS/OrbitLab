"""OrbitLab Conduit Pages."""

import reflex as rx

from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.layout import orbitlab_page

from .dialogs import CreateConduitEndpointDialog, CreateConduitPoolDialog, Dialogs
from .tables import ConduitEndpointsTable, ConduitPoolsTable


@rx.page("/conduit")
@orbitlab_page
def conduit_page() -> rx.Component:
    return rx.fragment(
        tailwind.PageHeader(
            "Conduit",
            tailwind.Buttons.Secondary(
                "Create Conduit Pool",
                icon="plus",
                on_click=CreateConduitPoolDialog.open,
            ),
            tailwind.Buttons.Primary(
                "Create Conduit Endpoint",
                icon="plus",
                on_click=CreateConduitEndpointDialog.open,
            ),
        ),
        ConduitPoolsTable(
            name="Pools",
            headers=["ID", "Name", "Sector", "Port", "Health", "Balance", ""],
            data=OrbitLabState.conduit_pools,
            refresh=OrbitLabState.cache_clear("conduit_pools"),
            class_name="w-1/2"
        ),
        ConduitEndpointsTable(
            name="Endpoints",
            headers=["ID", "Name", "Sector", "Type", "Port", "Pool", ""],
            data=OrbitLabState.conduit_endpoints,
            refresh=OrbitLabState.cache_clear("conduit_endpoints"),
            class_name="w-1/2"
        ),
        Dialogs(),
    )
