import reflex as rx

from orbitlab.data_types import ManifestKind
from orbitlab.manifest.client import ManifestClient
from orbitlab.web.components import PageHeader, SideBar

from .appliances import Appliances


class ComputePageState(rx.State):
    pass


class Dashboard:
    def __new__(cls) -> rx.Component:
        return PageHeader(
            "Compute Management",
        )
        # return rx.flex(
        #     Select(options={"Test 1": "1", "Test 2": "2"}),
        #     GridList(
        #         rx.foreach(range(20), lambda item: GridList.Item(rx.text(f"Test {item}"))),
        #         class_name="mt-6",
        #     ),
        #     direction="column",
        # )


@rx.page("/compute")
def compute() -> rx.Component:
    """Proxmox Nodes Page."""
    side_bar, sidebar_id = SideBar(
        SideBar.NavItem(icon="layout-dashboard", text="Dashboard"),
        SideBar.SectionHeader(title="LXC"),
        SideBar.NavItem(icon="circle-chevron-right", text="Appliances"),
        default_page="Dashboard",
        title="Compute",
    )
    return rx.el.div(
        side_bar,
        rx.el.div(
            rx.match(
                SideBar.Manager.registered[sidebar_id].active_page,
                ("Dashboard", Dashboard()),
                ("Appliances", Appliances()),
                Dashboard(),
            ),
            class_name=(
                "min-h-screen w-full flex flex-col p-4 "
                "bg-gradient-to-b from-white to-gray-100 "
                "dark:from-[#111317] dark:to-[#151820] "
                "text-gray-800 dark:text-[#E8F1FF] "
                "selection:bg-[#36E2F4]/40 selection:text-white "
                "backdrop-blur-sm transition-colors duration-300 ease-in-out"
            ),
        ),
        class_name="min-h-screen w-full flex",
    )
