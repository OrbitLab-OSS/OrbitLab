"""OrbitLab Network Dashboard Tables."""

from string import Template

import reflex as rx

from orbitlab.data_types import ConduitStatus, FrontendEvents, SectorStatus, WardLinkStatus
from orbitlab.proxmox import Proxmox
from orbitlab.redis.clients import ETCDClient, SecretsClient, SectorClient
from orbitlab.redis.models import Sector, SectorDomain, WardLinkClient
from orbitlab.web import tailwind
from orbitlab.web.global_state import InfrastructureManagementState, OrbitLabState
from orbitlab.web.utilities import EventGroup, create_workflow

from .dialogs import DeleteSectorDialog, AddSectorDomainDialog


WIREGUARD_CLIENT_FILE = Template("""
[Interface]
PrivateKey = $client_private_key
Address = $client_address
DNS = $sector_dns

[Peer]
PublicKey = $wardlink_public_key
AllowedIPs = $sector_cidr
Endpoint = $wardlink_lan_address:51820
PersistentKeepalive = 25
""")


class SectorsTable(tailwind.Table, EventGroup):
    """A table component for displaying Sectors (virtual networks)."""

    @staticmethod
    @rx.event
    async def create_conduit(_: rx.State, sector_id: str) -> FrontendEvents:
        if error := await create_workflow(name="sector.conduit.create", version="v1", payload={"id": sector_id}):
            return rx.toast.error(error)
        return rx.toast.info(f"Creating Conduit for Sector {sector_id}...")

    @staticmethod
    @rx.event
    async def update_conduit(_: rx.State, sector_id: str) -> FrontendEvents:
        if error := await create_workflow(name="sector.conduit.update", version="v1", payload={"id": sector_id}):
            return rx.toast.error(error)
        return rx.toast.info(f"Updating Conduit for Sector {sector_id}...")

    @staticmethod
    @rx.event
    async def create_wardlink(_: rx.State, sector_id: str) -> FrontendEvents:
        await SectorClient().get_wardlink_cidr(id=sector_id)  # Pre-seed cidr to catch errors before creation
        if error := await create_workflow(name="sector.wardlink.create", version="v1", payload={"id": sector_id}):
            return rx.toast.error(error)
        return rx.toast.info(f"Creating WardLink for Sector {sector_id}...")

    @staticmethod
    @rx.event
    async def update_gateway(_: rx.State, sector_id: str) -> FrontendEvents:
        if error := await create_workflow(name="sector.gateway.update", version="v1", payload={"id": sector_id}):
            return rx.toast.error(error)
        return rx.toast.info(f"Updating Gateway for Sector {sector_id}...")

    @staticmethod
    @rx.event
    async def view_in_proxmox(_: rx.State, vmid: int) -> FrontendEvents:
        return rx.redirect(
            await Proxmox().get_view_in_proxmox_url(vmid=vmid, compute_type="lxc"),
            is_external=True,
        )
    
    @staticmethod
    @rx.event
    async def view_dashboard(_: rx.State, vmid: int) -> FrontendEvents:
        proxmox = Proxmox()
        if address := await proxmox.get_ipv4_address(vmid=vmid, device="eth1"):
            return rx.redirect(f"http://{address.ip}:8080/dashboard", is_external=True)
        return rx.toast.error(f"Unable to determine eth1 address for {vmid}")

    @staticmethod
    @rx.event
    async def add_wardlink_client(_: rx.State, sector_id: str, name: str) -> FrontendEvents:
        client = await SectorClient().add_wardlink_client(id=sector_id, name=name)
        client_keys = await SecretsClient().get_wardlink_keypair(sector=sector_id, name=client.name)
        etcd_member = await ETCDClient().get_random_member()
        async with await Proxmox().create_connection() as connection:
            commands = [
                f"etcdctl put wardlink/{sector_id}/peers/{client.index}/public-key '{client_keys['public']}'",
                f"etcdctl put wardlink/{sector_id}/peers/{client.index}/address '{client.address}'",
            ]
            await connection.lxc_execute_script(vmid=etcd_member.vmid, content="\n".join(commands))
        
        return [
            SectorsTable.download_client_config(sector_id, client),
            OrbitLabState.cache_clear("sectors"),
        ]

    @staticmethod
    @rx.event
    async def download_client_config(_: rx.State, sector_id: str, client: WardLinkClient) -> FrontendEvents:
        sector = await SectorClient().get(id=sector_id)
        wardlink_lan_address = await Proxmox().get_ipv4_address(vmid=sector.state.wardlink_vmid, device="eth1")
        if not wardlink_lan_address:
            return rx.toast.error("Unable to get WardLink LAN address")
        
        client_keys = await SecretsClient().get_wardlink_keypair(sector=sector_id, name=client.name)
        server_keys = await SecretsClient().get_wardlink_keypair(sector=sector_id, name="server")
        
        wireguard_file = WIREGUARD_CLIENT_FILE.safe_substitute(
            client_private_key=client_keys["private"],
            client_address=f"{client.address.ip}/32",
            sector_dns=sector.config.dns_address.ip,
            wardlink_public_key=server_keys["public"],
            sector_cidr=sector.config.cidr_block,
            wardlink_lan_address=wardlink_lan_address.ip,
        )
        return rx.download(data=wireguard_file, filename=f"{sector.config.alias.replace(" ", "")}.wireguard.conf")

    @classmethod
    def _domain(cls, sector_domain: SectorDomain) -> rx.Component:
        return rx.el.div(
            rx.text(sector_domain.domain),
            tailwind.Badge(f"{sector_domain.domain_provider}", color_scheme="blue"),
            class_name="w-full flex items-center justify-between"
        )

    @classmethod
    def _wardlink_client(cls, sector_id: str, client: WardLinkClient) -> rx.Component:
        return tailwind.Menu.Item(
            client.name,
            on_click=lambda: cls.download_client_config(sector_id, client),
        )

    @classmethod
    def row(cls, sector: Sector) -> list[rx.Component | rx.Var]:
        """Create and return the table row component."""
        conduit_created = rx.Var.create(sector.state.conduit_vmid != 0)
        wardlink_created = rx.Var.create(sector.state.wardlink_vmid != 0)
        return [
            # TODO: Convert to link when implementing details pages.
            rx.text(sector.config.id),
            rx.text(sector.config.alias),
            tailwind.Badge(f"{sector.config.cidr_block}", color_scheme="blue"),
            rx.match(
                sector.state.gateway_status,
                (SectorStatus.AVAILABLE, tailwind.Badge(sector.state.gateway_status.capitalize(), color_scheme="green")),
                (SectorStatus.DELETING, tailwind.Badge(sector.state.gateway_status.capitalize(), color_scheme="red")),
                tailwind.Badge(sector.state.gateway_status.capitalize(), color_scheme="orange"),
            ),
            rx.match(
                sector.state.conduit_status,
                (
                    ConduitStatus.RUNNING,
                    tailwind.HoverCard(
                        tailwind.Badge(sector.state.conduit_status.capitalize(), color_scheme="green"),
                        rx.cond(
                            rx.Var.create(sector.config.domains).length() == 0,
                            rx.el.p("No configured domains."),
                            rx.el.div(
                                rx.foreach(
                                    sector.config.domains,
                                    lambda sector_domain: cls._domain(sector_domain=sector_domain),
                                ),
                                class_name="w-3xs flex flex-col space-y-3"
                            ),
                        ),
                    ),
                ),
                (ConduitStatus.DELETING, tailwind.Badge(sector.state.conduit_status.capitalize(), color_scheme="red")),
                tailwind.Badge(sector.state.conduit_status.capitalize(), color_scheme="orange"),
            ),
            rx.match(
                sector.state.wardlink_status,
                (WardLinkStatus.RUNNING, tailwind.Badge(sector.state.wardlink_status.capitalize(), color_scheme="green")),
                (WardLinkStatus.DELETING, tailwind.Badge(sector.state.wardlink_status.capitalize(), color_scheme="red")),
                tailwind.Badge(sector.state.wardlink_status.capitalize(), color_scheme="orange"),
            ),
            rx.el.div(
                rx.cond(
                    sector.state.gateway_version == InfrastructureManagementState.latest_version,
                    rx.icon("circle-check-big", class_name="text-[#16A34A] dark:text-[#4ADE80]"),
                    rx.icon("circle-alert", class_name="text-[#EA580C] dark:text-[#FB923C]"),
                ),
                rx.text(sector.state.gateway_version),
                class_name="flex space-x-4"
            ),
            rx.cond(
                sector.state.conduit_vmid != 0,
                rx.el.div(
                    rx.cond(
                        sector.state.conduit_version == InfrastructureManagementState.latest_version,
                        rx.icon("circle-check-big", class_name="text-[#16A34A] dark:text-[#4ADE80]"),
                        rx.icon("circle-alert", class_name="text-[#EA580C] dark:text-[#FB923C]"),
                    ),
                    rx.text(sector.state.conduit_version),
                    class_name="flex space-x-4"
                ),
                rx.icon("circle-x", class_name="text-[#DC2626] dark:text-[#F87171]"),
            ),
            rx.cond(
                sector.state.wardlink_vmid != 0,
                rx.el.div(
                    rx.cond(
                        sector.state.wardlink_version == InfrastructureManagementState.latest_version,
                        rx.icon("circle-check-big", class_name="text-[#16A34A] dark:text-[#4ADE80]"),
                        rx.icon("circle-alert", class_name="text-[#EA580C] dark:text-[#FB923C]"),
                    ),
                    rx.text(sector.state.wardlink_version),
                    class_name="flex space-x-4"
                ),
                rx.icon("circle-x", class_name="text-[#DC2626] dark:text-[#F87171]"),
            ),
            tailwind.Menu(
                tailwind.Buttons.Icon("ellipsis-vertical"),
                tailwind.Menu.SubMenu(
                    "Conduit",
                    tailwind.Menu.Item(
                        "Add Domain",
                        on_click=AddSectorDomainDialog.open(sector.config.id),
                        disabled=~conduit_created,
                    ),
                    tailwind.Menu.Separator(),
                    tailwind.Menu.Item(
                        "View in Proxmox",
                        on_click=cls.view_in_proxmox(sector.state.conduit_vmid),
                        disabled=~conduit_created,
                    ),
                    tailwind.Menu.Item(
                        "View Dashboard",
                        on_click=cls.view_dashboard(sector.state.conduit_vmid),
                        disabled=~conduit_created,
                    ),
                    tailwind.Menu.Separator(),
                    tailwind.Menu.Item(
                        "Create",
                        on_click=cls.create_conduit(sector.config.id),
                        disabled=conduit_created, # pyright: ignore[reportArgumentType]
                    ),
                    tailwind.Menu.Item(
                        rx.cond(
                            sector.state.conduit_version == InfrastructureManagementState.latest_version,
                            "No Update Available",
                            f"Update to v{InfrastructureManagementState.latest_version}",
                        ),
                        on_click=cls.update_conduit(sector.config.id),
                        disabled=sector.state.conduit_version == InfrastructureManagementState.latest_version,
                    ),
                ),
                tailwind.Menu.SubMenu(
                    "WardLink",
                    tailwind.Menu.Item(
                        "Add Client",
                        on_click=cls.add_wardlink_client(sector.config.id, "Test"),
                        disabled=~wardlink_created,
                    ),
                    rx.cond(
                        rx.Var.create(sector.state.wardlink_clients).length() > 0,
                        tailwind.Menu.SubMenu(
                            "Download Client Config",
                            rx.foreach(
                                sector.state.wardlink_clients.values(),
                                lambda client: cls._wardlink_client(sector.config.id, client),
                            )
                        ),
                        tailwind.Menu.Item(
                            "Download Client Config",
                            disabled=True,
                        ),
                    ),
                    tailwind.Menu.Separator(),
                    tailwind.Menu.Item(
                        "View in Proxmox",
                        on_click=cls.view_in_proxmox(sector.state.wardlink_vmid),
                        disabled=~wardlink_created,
                    ),
                    tailwind.Menu.Separator(),
                    tailwind.Menu.Item(
                        "Create",
                        on_click=cls.create_wardlink(sector.config.id),
                        disabled=wardlink_created, # pyright: ignore[reportArgumentType]
                    ),
                    tailwind.Menu.Item(
                        rx.cond(
                            sector.state.wardlink_version == InfrastructureManagementState.latest_version,
                            "No Update Available",
                            f"Update to v{InfrastructureManagementState.latest_version}",
                        ),
                        on_click=cls.update_conduit(sector.config.id),
                        disabled=sector.state.wardlink_version == InfrastructureManagementState.latest_version,
                    ),
                ),
                tailwind.Menu.SubMenu(
                    "Gateway",
                    tailwind.Menu.Item(
                        "View in Proxmox",
                        on_click=cls.view_in_proxmox(sector.state.gateway_vmid),
                    ),
                    tailwind.Menu.Separator(),
                    tailwind.Menu.Item(
                        rx.cond(
                            sector.state.gateway_version == InfrastructureManagementState.latest_version,
                            "No Update Available",
                            f"Update to v{InfrastructureManagementState.latest_version}",
                        ),
                        on_click=cls.update_gateway(sector.config.id),
                        disabled=sector.state.gateway_version == InfrastructureManagementState.latest_version,
                    ),
                ),
                tailwind.Menu.Separator(),
                tailwind.Menu.Item(
                    "Delete Sector",
                    on_click=DeleteSectorDialog.check_can_delete(sector.config.id),
                    danger=True,
                ),
            ),
        ]
