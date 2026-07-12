import reflex as rx

from orbitlab.data_types import BackplaneStatus, ETCDStatus, FrontendEvents, InitializationStatus
from orbitlab.web import tailwind
from orbitlab.web.components.dialogs import ConfirmUpdateInfrastructureDialog, UpgradeETCDDialog
from orbitlab.web.components.splash_page import SplashPage
from orbitlab.web.global_state import InfrastructureManagementState, OrbitLabState
from orbitlab.web.layout import orbitlab_page
from orbitlab.web.utilities import EventGroup, create_workflow


class InfrastructureCard:

    def __new__(cls) -> rx.Component:
        return tailwind.Card(
            rx.el.div(
                rx.el.div(               
                    rx.text("Latest Version:"),
                    rx.el.div(
                        rx.link(
                            InfrastructureManagementState.latest_version,
                            href=f"https://github.com/OrbitLab-OSS/Appliances/releases/tag/v{InfrastructureManagementState.latest_version}",
                            is_external=True,
                        ),
                        class_name="flex space-x-4"
                    ),
                    class_name="w-full flex items-center justify-between"
                ),
                rx.el.div(               
                    rx.text("Current Version:"),
                    rx.el.div(
                        rx.cond(
                            InfrastructureManagementState.infrastructure_update_available,
                            rx.icon("circle-alert", class_name="text-[#EA580C] dark:text-[#FB923C]"),
                            rx.icon("circle-check-big", class_name="text-[#16A34A] dark:text-[#4ADE80]"),
                        ),
                        rx.text(InfrastructureManagementState.current_version),
                        class_name="flex space-x-4"
                    ),
                    class_name="w-full flex items-center justify-between"
                ),
                class_name="w-full flex flex-col p-5 space-y-5"
            ),
            header=tailwind.Card.Header(
                rx.el.div(
                    rx.el.h1("Infrastructure"),
                    tailwind.Menu(
                        tailwind.WithStatus(
                            tailwind.Buttons.Icon("ellipsis-vertical"),
                            color="red",
                            animate=True,
                            disabled=~InfrastructureManagementState.infrastructure_update_available,
                        ),
                        tailwind.Menu.Item(
                            "Refresh",
                            on_click=InfrastructureManagementState.cache_clear("current_version")
                        ),
                        tailwind.Menu.Separator(),
                        tailwind.Menu.Item(
                            rx.cond(
                                InfrastructureManagementState.infrastructure_update_available,
                                f"Upgrade to v{InfrastructureManagementState.latest_version}",
                                "No Upgrade Available",
                            ),
                            disabled=~InfrastructureManagementState.infrastructure_update_available,
                            on_click=ConfirmUpdateInfrastructureDialog.open,
                        ),
                    ),
                    class_name="w-full flex items-center justify-between"
                ),
            ),
            class_name="mt-4"
        )


class BackplaneCard(EventGroup):
    
    @staticmethod
    @rx.event
    async def upgrade_backplane(_: rx.State) -> FrontendEvents:
        if error := await create_workflow(name="infrastructure.upgrade-backplane", version="v1", payload={}):
            return rx.toast.error(error)
        return rx.toast.info("Upgrading Backplane...")
    
    def __new__(cls) -> rx.Component:
        backplane_upgrade_available = InfrastructureManagementState.current_version != InfrastructureManagementState.backplane_version
        return tailwind.Card(
            rx.el.div(               
                rx.el.div(               
                    rx.text("Status:"),
                    rx.match(
                        InfrastructureManagementState.backplane_status,
                        (BackplaneStatus.AVAILABLE, tailwind.Badge("Available", color_scheme="green")),
                        (BackplaneStatus.UPDATING, tailwind.Badge("Updating", color_scheme="blue")),
                        tailwind.Badge(f"{InfrastructureManagementState.backplane_status}".capitalize()),
                    ),
                    class_name="w-full flex items-center justify-between"
                ),
                rx.el.div(               
                    rx.text("Version:"),
                    rx.el.div(
                        rx.cond(
                            backplane_upgrade_available,
                            rx.icon("circle-alert", class_name="text-[#EA580C] dark:text-[#FB923C]"),
                            rx.icon("circle-check-big", class_name="text-[#16A34A] dark:text-[#4ADE80]"),
                        ),
                        rx.text(InfrastructureManagementState.backplane_version),
                        class_name="flex space-x-4"
                    ),
                    class_name="w-full flex items-center justify-between"
                ),
                class_name="w-full flex flex-col p-5 space-y-5"
            ),
            header=tailwind.Card.Header(
                rx.el.div(
                    rx.el.h1("Backplane"),
                    tailwind.Menu(
                        tailwind.WithStatus(
                            tailwind.Buttons.Icon("ellipsis-vertical"),
                            color="red",
                            animate=True,
                            disabled=~backplane_upgrade_available,
                        ),
                        tailwind.Menu.Item(
                            "Refresh",
                            on_click=InfrastructureManagementState.cache_clear("backplane")
                        ),
                        tailwind.Menu.Separator(),
                        tailwind.Menu.Item(
                            rx.cond(
                                backplane_upgrade_available,
                                f"Upgrade to v{InfrastructureManagementState.current_version}",
                                "No Upgrade Available",
                            ),
                            disabled=~backplane_upgrade_available,
                            on_click=cls.upgrade_backplane,
                        ),
                    ),
                    class_name="w-full flex items-center justify-between"
                ),
            ),
            class_name="mt-4"
        )


class ETCDCard:

    def __new__(cls) -> rx.Component:
        etcd_upgrade_available = InfrastructureManagementState.current_version != InfrastructureManagementState.etcd_version
        return tailwind.Card(
            rx.el.div(               
                rx.el.div(               
                    rx.text("Status:"),
                    rx.match(
                        InfrastructureManagementState.etcd_status,
                        (ETCDStatus.AVAILABLE, tailwind.Badge("Available", color_scheme="green")),
                        (ETCDStatus.DEGRADED, tailwind.Badge("Degraded", color_scheme="orange")),
                        (ETCDStatus.UPGRADING, tailwind.Badge("Upgrading", color_scheme="blue")),
                        tailwind.Badge("Pending"),
                    ),
                    class_name="w-full flex items-center justify-between"
                ),
                rx.el.div(               
                    rx.text("Version:"),
                    rx.el.div(
                        rx.cond(
                            etcd_upgrade_available,
                            rx.icon("circle-alert", class_name="text-[#EA580C] dark:text-[#FB923C]"),
                            rx.icon("circle-check-big", class_name="text-[#16A34A] dark:text-[#4ADE80]"),
                        ),
                        rx.text(InfrastructureManagementState.etcd_version),
                        class_name="flex space-x-4"
                    ),
                    class_name="w-full flex items-center justify-between"
                ),
                class_name="w-full flex flex-col p-5 space-y-5"
            ),
            header=tailwind.Card.Header(
                rx.el.div(
                    rx.el.h1("ETCD Cluster"),
                    tailwind.Menu(
                        tailwind.WithStatus(
                            tailwind.Buttons.Icon("ellipsis-vertical"),
                            color="red",
                            animate=True,
                            disabled=~etcd_upgrade_available,
                        ),
                        tailwind.Menu.Item(
                            "Refresh",
                            on_click=[
                                InfrastructureManagementState.cache_clear("etcd_status"),
                                InfrastructureManagementState.cache_clear("etcd_version"),
                            ]
                        ),
                        tailwind.Menu.Separator(),
                        tailwind.Menu.Item(
                            rx.cond(
                                etcd_upgrade_available,
                                f"Upgrade to v{InfrastructureManagementState.current_version}",
                                "No Upgrade Available",
                            ),
                            disabled=~etcd_upgrade_available,
                            on_click=UpgradeETCDDialog.open,
                        ),
                    ),
                    class_name="w-full flex items-center justify-between"
                ),
            ),
            class_name="mt-4"
        )


@orbitlab_page
def main_dashboard() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            InfrastructureCard(),
            BackplaneCard(),
            ETCDCard(),
            class_name="w-full grid grid-cols-3 gap-3"
        ),
        class_name="w-full flex space-x-6",
    )


@rx.page("/")
def home() -> rx.Component:
    """Home page that displays either the main dashboard or splash page based on configuration status."""
    return rx.cond(OrbitLabState.status == InitializationStatus.COMPLETE, main_dashboard(), SplashPage())
