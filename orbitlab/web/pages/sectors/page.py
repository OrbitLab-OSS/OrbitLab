"""OrbitLab Networks Dashboard Pages."""

from typing import ClassVar

import reflex as rx

from orbitlab.data_types import ConduitStatus, FrontendEvents, SectorStatus, WardLinkStatus
from orbitlab.proxmox import Proxmox
from orbitlab.redis.clients import SectorClient
from orbitlab.redis.models import Sector
from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.layout import orbitlab_page
from orbitlab.web.utilities import EventGroup

from .dialogs import CreateSectorDialog, DeleteSectorDialog, AddSectorDomainDialog
from .tables import SectorsTable


class SectorDetailsPageState(rx.State):
    details_sector_id: ClassVar[str]
    
    @rx.var
    async def sector(self) -> Sector | None:
        if self.details_sector_id:
            return await SectorClient().get(id=self.details_sector_id)

    @rx.event
    async def view_in_proxmox(self) -> FrontendEvents | None:
        if sector := await self.sector:
            return rx.redirect(
                await Proxmox().get_view_in_proxmox_url(vmid=sector.state.gateway_vmid, compute_type="lxc"),
                is_external=True,
            )


class OverviewTab(EventGroup):
    
    @classmethod
    def health_card(cls) -> rx.Component:
        gateway_status = SectorDetailsPageState.sector.state.to(dict).gateway_status.to(str)
        conduit_status = SectorDetailsPageState.sector.state.to(dict).conduit_status.to(str)
        wardlink_status = SectorDetailsPageState.sector.state.to(dict).wardlink_status.to(str)
        return tailwind.Card(
            rx.el.div(
                rx.el.div(
                    rx.text("Gateway:"),
                    rx.match(
                        gateway_status,
                        (
                            SectorStatus.AVAILABLE,
                            tailwind.Badge(
                                gateway_status.capitalize(),
                                color_scheme="green",
                            ),
                        ),
                        (
                            SectorStatus.DELETING,
                            tailwind.Badge(
                                gateway_status.capitalize(),
                                color_scheme="red",
                            ),
                        ),
                        tailwind.Badge(
                            gateway_status.capitalize(),
                            color_scheme="orange",
                        ),
                    ),
                    class_name="flex items-center space-x-5"
                ),
                rx.el.div(
                    rx.text("Conduit:"),
                    rx.match(
                        conduit_status,
                        (
                            ConduitStatus.RUNNING,
                            tailwind.Badge(
                                conduit_status.capitalize(),
                                color_scheme="green",
                            ),
                        ),
                        (
                            ConduitStatus.DELETING,
                            tailwind.Badge(
                                conduit_status.capitalize(),
                                color_scheme="red",
                            ),
                        ),
                        tailwind.Badge(
                            conduit_status.capitalize(),
                            color_scheme="orange",
                        ),
                    ),
                    class_name="flex items-center space-x-5"
                ),
                rx.el.div(
                    rx.text("WardLink:"),
                    rx.match(
                        wardlink_status,
                        (
                            WardLinkStatus.RUNNING,
                            tailwind.Badge(
                                wardlink_status.capitalize(),
                                color_scheme="green",
                            ),
                        ),
                        (
                            WardLinkStatus.DELETING,
                            tailwind.Badge(
                                wardlink_status.capitalize(),
                                color_scheme="red",
                            ),
                        ),
                        tailwind.Badge(
                            wardlink_status.capitalize(),
                            color_scheme="orange",
                        ),
                    ),
                    class_name="flex items-center space-x-5"
                ),
                class_name="w-full flex items-center justify-between px-5 py-3"
            ),
            header=tailwind.Card.Header(rx.text("Health"))
        )
                
    @classmethod
    def proxmox_network_card(cls) -> rx.Component:
        return tailwind.Card(
            header=tailwind.Card.Header(rx.text("Proxmox VXLAN"))
        )
    
    def __new__(cls) -> rx.Component:
        return rx.el.div(
            cls.health_card(),
        )


@rx.page("/sectors/[details_sector_id]")
@orbitlab_page
def sectors_details() -> rx.Component:
    """Render the sector details page."""
    
    return rx.el.div(
        tailwind.PageHeader(
            rx.el.div(
                rx.el.h2(
                    f"{SectorDetailsPageState.sector.config.alias}",
                    class_name="text-2xl font-bold tracking-tight text-gray-900 dark:text-[#E8F1FF]",
                ),
                tailwind.Badge(SectorDetailsPageState.sector.config.id),
                tailwind.Badge(SectorDetailsPageState.sector.config.cidr_block, color_scheme="blue"),
                class_name="w-full flex items-center space-x-5",
            ),
        ),
        tailwind.Tabs(
            tailwind.Tabs.Tab(
                name="Overview",
                value="overview",
                content=OverviewTab(),
            ),
            tailwind.Tabs.Tab(
                name="Conduit",
                value="conduit",
                content=rx.el.div("conduit")
            ),
            tailwind.Tabs.Tab(
                name="WardLink",
                value="wardlink",
                content=rx.el.div("wardlink")
            ),
            tailwind.Tabs.Tab(
                name="VIPs",
                value="vips",
                content=rx.el.div("vips")
            ),
            tailwind.Tabs.Tab(
                name="DNS",
                value="dns",
                content=rx.el.div("dns")
            ),
            default_value="overview"
        )
    )


@rx.page("/sectors")
@orbitlab_page
def sectors_dashboard() -> rx.Component:
    """Render the networks management dashboard page."""
    return rx.el.div(
        tailwind.PageHeader(
            "Sector Management",
            tailwind.Buttons.Primary(
                "Create Sector",
                icon="plus",
                on_click=tailwind.Dialog.open(CreateSectorDialog.dialog_id),
            ),
        ),
        SectorsTable(
            name="Sectors",
            headers=["ID", "Name", "CIDR Block", "Gateway Status", "Conduit Status", "WardLink Status", "Gateway Version", "Conduit Version", "WardLink Version", ""],
            data=OrbitLabState.sectors,
            refresh=OrbitLabState.cache_clear("sectors"),
        ),
        CreateSectorDialog(),
        DeleteSectorDialog(),
        AddSectorDomainDialog(),
    )
