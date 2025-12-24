"""OrbitLab Web UI."""

import reflex as rx

from orbitlab.data_types import InitializationState
from orbitlab.web import components
from orbitlab.web.pages import pages  # noqa: F401

from .splash_page import SplashPage, SplashPageState


class HomePageState(rx.State):
    """State management for the home page."""

    loading: bool = True


class MainDashboard:
    """Main dashboard component that creates the application layout with sidebar and content area."""

    def __new__(cls) -> rx.Component:
        """Create and return the page."""
        return rx.el.div(
            components.SideBar(
                components.SideBar.NavItem(icon="server", text="Proxmox Nodes", href="/nodes"),
                components.SideBar.NavItem(icon="server-cog", text="Compute", href="/compute"),
                components.SideBar.NavItem(icon="book-lock", text="Secrets & PKI", href="/secrets-pki"),
                components.SideBar.NavItem(icon="network", text="Sectors", href="/sectors"),
            ),
            rx.el.div(
                class_name=(
                    "min-h-screen w-full flex flex-col p-4 "
                    "bg-gradient-to-b from-gray-200 to-gray-400 "
                    "dark:from-[#111317] dark:to-[#151820] "
                    "text-gray-800 dark:text-[#E8F1FF] "
                    "selection:bg-[#36E2F4]/40 selection:text-white "
                    "backdrop-blur-sm transition-colors duration-300 ease-in-out"
                ),
            ),
            class_name="min-h-screen w-full flex",
        )


@rx.page("/")
def home() -> rx.Component:
    """Home page that displays either the main dashboard or splash page based on configuration status."""
    return rx.cond(
        SplashPageState.initialization_state == InitializationState.COMPLETE,
        MainDashboard(),
        SplashPage(),
    )


app = rx.App(
    stylesheets=["animations.css"],
)
