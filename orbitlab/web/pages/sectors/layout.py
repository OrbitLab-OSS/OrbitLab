"""OrbitLab Networks Layout."""

from collections.abc import Callable

import reflex as rx

from orbitlab.web.components.sidebar import SideBar
from orbitlab.web.pages.layout import DefaultLayout
from orbitlab.web.utilities import require_configuration


def sectors_page(page: Callable[[], rx.Component]) -> Callable[[], rx.Component]:
    """Create a networks page layout with sidebar navigation."""

    @require_configuration
    def wrapped() -> rx.Component:
        return DefaultLayout(
            SideBar(
                SideBar.NavItem(icon="layout-dashboard", text="Dashboard", href="/sectors"),
                title="Sectors",
            ),
            page(),
        )

    return wrapped
