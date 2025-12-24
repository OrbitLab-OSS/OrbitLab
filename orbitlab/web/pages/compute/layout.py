"""OrbitLab Compute Page Layout."""
from collections.abc import Callable

import reflex as rx

from orbitlab.web.components.sidebar import SideBar
from orbitlab.web.pages.layout import DefaultLayout
from orbitlab.web.utilities import require_configuration


def compute_page(page: Callable[[], rx.Component]) -> Callable[[], rx.Component]:
    """Create a compute page with sidebar navigation."""

    @require_configuration
    def wrapped() -> rx.Component:
        return DefaultLayout(
            SideBar(
                SideBar.NavItem(icon="layout-dashboard", text="Dashboard", href="/compute"),
                SideBar.SectionHeader(title="LXC"),
                SideBar.NavItem(icon="circle-chevron-right", text="Appliances", href="/compute/lxc/appliances"),
                title="Compute",
            ),
            page(),
        )

    return wrapped
