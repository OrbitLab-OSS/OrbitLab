import reflex as rx

from orbitlab.web.components import PageHeader, SideBar
from orbitlab.web.components.sortable import Sortable, SortableItem

from .appliances import Appliances


class ComputePageState(rx.State):
    data_order: list[SortableItem] = rx.field(default_factory=list)
    data_config: dict[str, dict] = rx.field(default_factory=dict)


@rx.event
async def update_order(state: ComputePageState, data: list[SortableItem]):
    state.data_order = data


@rx.event
async def add_item(state: ComputePageState):
    new_item_id = len(state.data_order)
    while new_item_id in state.data_config:
        new_item_id += 1
    state.data_order.append({"id": new_item_id, "metadata": {"name": f"Item {new_item_id}"}})
    state.data_config[new_item_id] = {}


@rx.event
async def modify_item(state: ComputePageState, item_id: int):
    print(state.data_config[item_id])


@rx.event
async def delete_item(state: ComputePageState, item_id: int):
    del state.data_config[item_id]
    item = next((item for item in state.data_order if item["id"] == item_id), None)
    state.data_order.remove(item)


def sortable_item() -> rx.Component:
    return rx.el.div(
        rx.icon("grip-vertical", class_name="drag-handle ml-2 mr-4 cursor-pointer"),
        rx.el.div(
            rx.button("Test", on_click=lambda: modify_item(Sortable.SortID)),
            rx.button("Remove", on_click=lambda: delete_item(Sortable.SortID)),
            class_name="flex space-x-5",
        ),
        key=Sortable.SortID,
        class_name="flex",
    )


class Dashboard:
    def __new__(cls) -> rx.Component:
        return rx.el.div(
            PageHeader(
                "Compute Management",
            ),
            class_name="w-full h-full",
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
def compute_page() -> rx.Component:
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
            ),
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
