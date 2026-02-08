"""OrbitLab Compute Page Layout."""

from collections.abc import Callable

import reflex as rx

from orbitlab.web.components.sidebar import SideBar
from orbitlab.web.pages.layout import DefaultLayout
from orbitlab.web.splash_page import require_configuration


def compute_page(page: Callable[[], rx.Component]) -> Callable[[], rx.Component]:
    """Create a compute page with sidebar navigation."""

    @require_configuration
    def wrapped() -> rx.Component:
        return DefaultLayout(
            SideBar(
                SideBar.NavItem(icon="layout-dashboard", text="Dashboard", href="/compute"),
                SideBar.SectionHeader(title="LXC"),
                SideBar.NavItem(icon="cpu", text="Instances", href="/compute/lxc/instances"),
                SideBar.NavItem(icon="file-box", text="Appliances", href="/compute/lxc/appliances"),
                SideBar.SectionHeader(title="VM"),
                SideBar.NavItem(icon="cpu", text="Instances", href="/compute/vm/instances"),
                SideBar.NavItem(icon="hard-drive", text="Images", href="/compute/vm/images"),
                SideBar.SectionHeader(title="Autoscaling"),
                SideBar.NavItem(icon="server-cog", text="VM Pools", href="/compute/autoscaling"),
                title="Compute",
            ),
            page(),
        )

    return wrapped
