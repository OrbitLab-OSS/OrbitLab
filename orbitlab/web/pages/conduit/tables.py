import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.proxmox import Proxmox
from orbitlab.redis.clients import SectorClient
from orbitlab.redis.models import ConduitEndpoint, ConduitPool, InstanceTarget
from orbitlab.web import tailwind
from .dialogs import DeleteConduitEndpointDialog, DeleteConduitPoolDialog, UpdateConduitPoolHealthCheckDialog
from orbitlab.web.utilities import EventGroup


class ConduitPoolsTable(tailwind.Table, EventGroup):
    """A table component for displaying Conduit Pools."""

    @staticmethod
    @rx.event
    async def view_in_traefik(_: rx.State, sector: str, type: str, id: str) -> FrontendEvents:
        vmid = await SectorClient().get_vmid(id=sector, appliance="conduit")
        if address := await Proxmox().get_ipv4_address(vmid=vmid, device="eth1"):
            return rx.redirect(f"http://{address.ip}:8080/dashboard#/{type}/services/{id}@etcd", is_external=True)
        return rx.toast.error(f"Unable to determine requisite address for {sector} conduit")

    @classmethod
    def pool_target(cls, pool: ConduitPool, target: InstanceTarget) -> rx.Component:
        return rx.el.div(
            rx.text(target.instance_id),
            rx.text(target.weight),
            rx.cond(
                pool.state.targets_health.get(target.instance_id) == "UP",
                tailwind.Badge("UP", color_scheme="green"),
                tailwind.Badge("DOWN", color_scheme="red"),
            ),
            class_name="w-full flex justify-between"
        )

    @classmethod
    def row(cls, pool: ConduitPool) -> list[rx.Component]:
        """Create and return the table row component."""
        health_check_port = rx.cond(pool.config.health_check.port, pool.config.health_check.port, pool.config.port)
        return [
            rx.text(pool.config.id),
            rx.text(pool.config.name),
            rx.text(f"{pool.config.sector_name} ({pool.config.sector})"),
            rx.text(pool.config.port),
            tailwind.HoverCard(
                rx.el.div(
                    rx.match(
                        pool.state.health,
                        ("Unused", tailwind.Badge("UNUSED")),
                        ("Degraded", tailwind.Badge("DEGREADED", color_scheme="orange")),
                        ("Unhealthy", tailwind.Badge("UNHEALTHY", color_scheme="red")),
                        tailwind.Badge("HEALTHY", color_scheme="green")
                    ),
                ),
                rx.el.div(
                    rx.el.div(
                        tailwind.Badge(pool.config.health_check.method, color_scheme="blue"),
                        rx.text(f":{health_check_port}"),
                        rx.text(pool.config.health_check.path),
                        rx.text("->"),
                        rx.text(pool.config.health_check.expected_status),
                        class_name="w-full flex justify-between border border-b border-black dark:border-white"
                    ),
                    rx.cond(
                        pool.state.health != "Unused",
                        rx.fragment(
                            rx.el.div(
                                rx.text("Instance ID"),
                                rx.text("Weight"),
                                rx.text("Health"),
                                class_name="w-full flex justify-between underline underline-offset-4 mt-5"
                            ),
                            rx.foreach(pool.config.targets, lambda target: cls.pool_target(pool, target)),
                        ),
                    ),
                    class_name="w-sm flex-col space-y-1 items-center",
                ),
            ),
            tailwind.Badge(
                rx.match(
                    pool.config.balance,
                    ("wrr", "Weighted Round Robin"),
                    ("p2c", "Power of Two Choices"),
                    ("hrw", "Highest Random Weight"),
                    "Least-Time",
                ), 
                color_scheme="blue",
            ),
            tailwind.Menu(
                tailwind.Buttons.Icon("ellipsis-vertical"),
                tailwind.Menu.Item(
                    "Update Health Check",
                    on_click=UpdateConduitPoolHealthCheckDialog.open(pool.config.id),
                ),
                tailwind.Menu.Separator(),
                tailwind.Menu.Item(
                    "View in Traefik",
                    on_click=cls.view_in_traefik(pool.config.sector, pool.config.type, pool.config.id),
                ),
                tailwind.Menu.Separator(),
                tailwind.Menu.Item(
                    "Delete",
                    on_click=DeleteConduitPoolDialog.open(pool.config.id),
                    danger=True
                ),
            )
        ]


class ConduitEndpointsTable(tailwind.Table, EventGroup):
    """A table component for displaying Conduit Endpoints."""

    @staticmethod
    @rx.event
    async def view_in_traefik(_: rx.State, sector: str, type: str, id: str) -> FrontendEvents:
        router_type = "http" if "http" in type else type
        vmid = await SectorClient().get_vmid(id=sector, appliance="conduit")
        if address := await Proxmox().get_ipv4_address(vmid=vmid, device="eth1"):
            return rx.redirect(f"http://{address.ip}:8080/dashboard#/{router_type}/routers/{id}-{type}@etcd", is_external=True)
        return rx.toast.error(f"Unable to determine requisite address for {sector} conduit")

    @classmethod
    def row(cls, endpoint: ConduitEndpoint) -> list[rx.Component]:
        """Create and return the table row component."""
        return [
            rx.text(endpoint.config.id),
            rx.text(endpoint.config.name),
            rx.text(f"{endpoint.config.sector_name} ({endpoint.config.sector})"),
            rx.text(endpoint.config.type, class_name="uppercase"),
            rx.text(endpoint.config.port),
            rx.text(f"{endpoint.config.pool_name} ({endpoint.config.pool})"),
            tailwind.Menu(
                tailwind.Buttons.Icon("ellipsis-vertical"),
                tailwind.Menu.Item(
                    "View in Traefik",
                    on_click=cls.view_in_traefik(endpoint.config.sector, endpoint.config.type, endpoint.config.id),
                ),
                tailwind.Menu.Separator(),
                tailwind.Menu.Item(
                    "Delete",
                    on_click=DeleteConduitEndpointDialog.open(endpoint.config.id),
                    danger=True
                ),
            ),
        ]
