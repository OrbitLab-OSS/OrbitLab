"""OrbitLab Network Dashboard Tables."""

import reflex as rx

from orbitlab.data_types import SectorStatus
from orbitlab.redis.models import Sector
from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.utilities import EventGroup

from .dialogs import DeleteSectorDialog


class SectorsTable(EventGroup):
    """A table component for displaying virtual networks in the dashboard."""

    @classmethod
    def __table_row__(cls, sector: Sector) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                sector.config.id,  # Sector ID
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                sector.config.alias,  # Sector Name
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.match(
                    sector.state.status,
                    (SectorStatus.AVAILABLE, tailwind.Badge(sector.state.status.capitalize(), color_scheme="green")),
                    (SectorStatus.DELETING, tailwind.Badge(sector.state.status.capitalize(), color_scheme="red")),
                    tailwind.Badge(sector.state.status.capitalize(), color_scheme="orange"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                tailwind.Badge(f"{sector.config.cidr_block}", color_scheme="blue"),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                sector.config.tag,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                tailwind.Menu(
                    tailwind.Buttons.Icon("ellipsis-vertical"),
                    tailwind.Menu.Item(
                        "Delete Sector",
                        on_click=DeleteSectorDialog.check_can_delete(sector.config.id),
                        danger=True,
                    ),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            class_name=(
                "transition-colors duration-200 "
                "hover:bg-gray-100/60 dark:hover:bg-white/[0.06] "
                "hover:text-gray-900 dark:hover:text-[#E8F1FF]"
            ),
        )

    def __new__(cls) -> rx.Component:
        """Create and return the appliance templates table component."""
        header_class = (
            "px-6 py-3 text-left text-xs font-semibold tracking-wider uppercase text-gray-600 dark:text-[#AEB9CC]"
        )
        return tailwind.Card(
            rx.el.div(
                rx.el.table(
                    rx.el.thead(
                        rx.el.tr(
                            rx.el.th("ID", class_name=header_class),
                            rx.el.th("Name", class_name=header_class),
                            rx.el.th("Status", class_name=header_class),
                            rx.el.th("CIDR Block", class_name=header_class),
                            rx.el.th("VLAN Tag", class_name=header_class),
                            rx.el.th("", class_name=header_class),  # Menu Column
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(OrbitLabState.sectors, lambda network: cls.__table_row__(network)),
                        class_name=(
                            "divide-y divide-gray-200 dark:divide-white/[0.08] bg-white/70 dark:bg-[#0E1015]/60 "
                            "backdrop-blur-sm"
                        ),
                    ),
                    class_name=(
                        "min-w-full text-sm text-gray-800 dark:text-gray-200 "
                        "divide-y divide-gray-200 dark:divide-white/[0.08]"
                    ),
                ),
                class_name=(
                    "border border-gray-200 dark:border-white/[0.08] "
                    "rounded-b-xl overflow-x-auto shadow-md "
                    "bg-gradient-to-b from-white/90 to-gray-50/70 "
                    "dark:from-[#0E1015]/80 dark:to-[#12141A]/80 "
                    "hover:ring-1 hover:ring-[#36E2F4]/40 "
                    "transition-all duration-200"
                ),
            ),
            DeleteSectorDialog(),
            header=tailwind.Card.Header(
                rx.el.div(
                    rx.el.h3("Sectors"),
                    rx.el.div(
                        tailwind.Buttons.Icon("refresh-ccw", on_click=OrbitLabState.cache_clear("sectors")),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between",
                ),
            ),
            class_name="w-full mt-6",
        )
