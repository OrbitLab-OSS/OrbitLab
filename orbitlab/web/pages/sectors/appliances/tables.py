"""OrbitLab Sector Appliances Tables."""

from collections.abc import AsyncGenerator

import reflex as rx

from orbitlab.data_types import FrontendEvents, OrbitLabApplianceType
from orbitlab.web import components
from orbitlab.web.utilities import EventGroup

from .states import SectorAppliancesTableState


class StatusTable(EventGroup):
    """A table component for displaying the status of sector appliances."""

    @staticmethod
    @rx.event
    async def refresh(_: rx.State) -> FrontendEvents:
        """Refresh the cached data for all sector appliances."""
        return [
            SectorAppliancesTableState.cache_clear("sector_gateway"),
            SectorAppliancesTableState.cache_clear("sector_dns"),
            SectorAppliancesTableState.cache_clear("backplane_dns"),
            SectorAppliancesTableState.cache_clear("latest_versions"),
        ]

    @staticmethod
    @rx.event
    async def download(_: rx.State, appliance_type: OrbitLabApplianceType) -> AsyncGenerator[FrontendEvents, None]:
        """Download and update the specified appliance type."""
        yield SectorAppliancesTableState.download_appliance(appliance_type)
        match appliance_type:
            case OrbitLabApplianceType.SECTOR_GATEWAY:
                yield SectorAppliancesTableState.cache_clear("sector_gateway")
            case OrbitLabApplianceType.SECTOR_DNS:
                yield SectorAppliancesTableState.cache_clear("sector_dns")
            case OrbitLabApplianceType.BACKPLANE_DNS:
                yield SectorAppliancesTableState.cache_clear("backplane_dns")
        yield rx.toast.success(f"Updated {appliance_type} appliance.")

    @classmethod
    def __table_row__(
        cls,
        appliance_type: OrbitLabApplianceType,
        latest_version: rx.Var[str],
        downloaded_version: rx.Var[str],
    ) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                appliance_type,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.text(downloaded_version, size="3"),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.el.div(
                    rx.text(latest_version, size="3"),
                    rx.cond(
                        latest_version == "Err",
                        rx.link(
                            rx.icon("external-link"),
                            is_external=True,
                            href=f"https://github.com/OrbitLab-OSS/{appliance_type}/releases",
                        ),
                        rx.link(
                            rx.icon("external-link"),
                            is_external=True,
                            href=f"https://github.com/OrbitLab-OSS/{appliance_type}/releases/tag/v{latest_version}",
                        ),
                    ),
                    class_name="w-full flex items-center space-x-5",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                components.Menu(
                    components.Buttons.Icon("ellipsis-vertical"),
                    components.Menu.Item("Update Appliance", on_click=cls.download(appliance_type)),
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
        return components.Card(
            rx.el.div(
                rx.el.table(
                    rx.el.thead(
                        rx.el.tr(
                            rx.el.th("Appliance Type", class_name=header_class),
                            rx.el.th("Downloaded Version", class_name=header_class),
                            rx.el.th("Latest Version", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        cls.__table_row__(
                            appliance_type=OrbitLabApplianceType.SECTOR_GATEWAY,
                            latest_version=SectorAppliancesTableState.latest_sector_gateway_version,
                            downloaded_version=SectorAppliancesTableState.sector_gateway,
                        ),
                        cls.__table_row__(
                            appliance_type=OrbitLabApplianceType.SECTOR_DNS,
                            latest_version=SectorAppliancesTableState.latest_sector_dns_version,
                            downloaded_version=SectorAppliancesTableState.sector_dns,
                        ),
                        cls.__table_row__(
                            appliance_type=OrbitLabApplianceType.BACKPLANE_DNS,
                            latest_version=SectorAppliancesTableState.latest_backplane_dns_version,
                            downloaded_version=SectorAppliancesTableState.backplane_dns,
                        ),
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
            header=components.Card.Header(
                rx.el.div(
                    rx.el.h3("Sector Appliances"),
                    rx.el.div(
                        components.Buttons.Icon(
                            "refresh-ccw",
                            on_click=cls.refresh,
                        ),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between",
                ),
            ),
            class_name="w-full mt-6",
        )
