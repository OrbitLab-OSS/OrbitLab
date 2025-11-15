"""OrbitLab Web UI."""

import reflex as rx

from orbitlab.web.components.sidebar import SideBar
from orbitlab.web.components.splash_page import SplashPage, SplashPageState
from orbitlab.web.pages import pages


class HomePageState(rx.State):
    loading: bool = True


class MainDashboard:
    def __new__(cls) -> rx.Component:
        side_bar, sidebar_id = SideBar(
            SideBar.NavItem(icon="server", text="Proxmox Nodes", href="/nodes"),
            SideBar.NavItem(icon="server-cog", text="Compute", href="/compute"),
            SideBar.NavItem(icon="server-cog", text="Secrets & PKI", href="/secrets-pki"),
            default_page="",
        )
        return rx.el.div(
            side_bar,
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
    return rx.cond(
        SplashPageState.configured,
        MainDashboard(),
        SplashPage(),
    )


for page in (home, *pages):
    if "return" not in page.__annotations__:
        msg = f"Page {page.__name__} does not have a specified return type."
        raise RuntimeError(msg)
    if page.__annotations__["return"] != rx.Component:
        msg = f"Page {page.__name__} must return an rx.Component."
        raise RuntimeError(msg)

app = rx.App(
    stylesheets=["animations.css"],
)
