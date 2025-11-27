"""OrbitLab Nodes Management Layout."""

from collections.abc import Callable

import reflex as rx

from orbitlab.web.components.sidebar import SideBar
from orbitlab.web.pages.layout import DefaultLayout


def nodes_page(page: Callable[[], rx.Component]) -> rx.Component:
    """Create a nodes page layout wrapper."""

    def wrapped() -> rx.Component:
        return DefaultLayout(
            SideBar(
                SideBar.NavItem(icon="layout-dashboard", text="Dashboard", href="/nodes"),
                title="Nodes",
            ),
            page(),
        )

    return wrapped
