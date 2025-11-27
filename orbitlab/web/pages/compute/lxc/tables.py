"""OrbitLab LXC Tables."""

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.manifest.schemas.appliances import BaseApplianceManifest
from orbitlab.services.discovery.appliances import ApplianceDiscovery
from orbitlab.web.components import Buttons, Card, Menu
from orbitlab.web.states.utilities import EventGroup

from .dialogs import CreateApplianceDialog
from .states import AppliancesState, get_base_appliances


class BaseApplianceTable(EventGroup):
    """A table component for displaying base appliance manifests.

    This class provides functionality to display base appliances in a table format
    with refresh capabilities and discovery management features.
    """

    @staticmethod
    @rx.event
    async def refresh_base_appliances(state: AppliancesState) -> None:
        """Refresh the base appliances list by fetching the latest data."""
        state.base_appliances = get_base_appliances()

    @staticmethod
    @rx.event
    async def run_appliance_discovery(_: AppliancesState) -> FrontendEvents:
        """Run appliance discovery and refresh the base appliances list."""
        await ApplianceDiscovery().run()
        return BaseApplianceTable.refresh_base_appliances

    @classmethod
    def __table_row__(cls, appliance: BaseApplianceManifest) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                appliance.name,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.cond(
                    appliance.metadata.turnkey,
                    rx.badge(
                        "TurnKey",
                        class_name=(
                            "bg-[#36E2F4]/15 text-[#36E2F4] border border-[#36E2F4]/30 "
                            "dark:bg-[#36E2F4]/20 dark:text-[#36E2F4]"
                        ),
                    ),
                    rx.badge(
                        "System",
                        class_name=(
                            "bg-[#1E63E9]/15 text-[#1E63E9] border border-[#1E63E9]/30 "
                            "dark:bg-[#1E63E9]/20 dark:text-[#1E63E9]"
                        ),
                    ),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                appliance.spec.os_type,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                appliance.spec.version,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                appliance.spec.architecture,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                appliance.spec.storage,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                appliance.metadata.section,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                Menu(
                    Buttons.Icon("ellipsis-vertical"),
                    Menu.Item(
                        "Create Custom Appliance",
                        on_click=CreateApplianceDialog.create_appliance_from_base(appliance.name),
                    ),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
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
        return Card(
            rx.el.div(
                rx.el.table(
                    # === Table Header ===
                    rx.el.thead(
                        rx.el.tr(
                            rx.el.th("Name", class_name=header_class),
                            rx.el.th("Type", class_name=header_class),
                            rx.el.th("OS", class_name=header_class),
                            rx.el.th("Version", class_name=header_class),
                            rx.el.th("Arch", class_name=header_class),
                            rx.el.th("Storage", class_name=header_class),
                            rx.el.th("Section", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    # === Table Body ===
                    rx.el.tbody(
                        rx.foreach(AppliancesState.base_appliances, lambda app: cls.__table_row__(app)),
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
            header=Card.Header(
                rx.el.div(
                    rx.el.h3("Base Appliances"),
                    rx.el.div(
                        Buttons.Icon("refresh-ccw", on_click=cls.refresh_base_appliances),
                        Menu(
                            Buttons.Primary("Manage", icon="chevron-down"),
                            Menu.Item("Rerun Discovery", on_click=cls.run_appliance_discovery),
                        ),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between",
                ),
            ),
            class_name="w-full mt-6",
        )
