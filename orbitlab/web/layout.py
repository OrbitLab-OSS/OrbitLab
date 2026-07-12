"""OrbitLab Layout."""

from collections.abc import Callable

import reflex as rx

from orbitlab.data_types import InitializationStatus
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.components.sidebar import SideBar


def require_configuration(page: Callable[[], rx.Component]) -> Callable[[], rx.Component]:
    """Decorator to require that the configuration is complete before rendering the page."""

    def wrapped() -> rx.Component:
        return rx.cond(
            OrbitLabState.status == InitializationStatus.COMPLETE,
            page(),
            rx.el.div(on_mount=rx.redirect("/")),
        )

    return wrapped


def orbitlab_page(page: Callable[[], rx.Component]) -> Callable[[], rx.Component]:
    """Create layout wrapper."""

    @require_configuration
    def wrapped() -> rx.Component:
        return rx.el.div(
            SideBar(
                SideBar.Section(icon="server", text="Proxmox Nodes", href="/nodes"),
                SideBar.Section(
                    text="Compute",
                    href="/compute",
                    icon="cpu",
                    children=[
                        SideBar.Header(title="Templates"),
                        SideBar.NavItem(icon="file-box", text="Appliances", href="/compute/appliances"),
                        SideBar.NavItem(icon="hard-drive", text="Images", href="/compute/images"),
                        SideBar.Header(title="Autoscaling"),
                        SideBar.NavItem(icon="server-cog", text="VM Pools", href="/compute/autoscaling"),
                    ]
                ),
                SideBar.Section(
                    icon="book-lock",
                    text="Secrets & PKI",
                    href="/secrets-pki",
                    children=[
                        SideBar.Header(title="Secrets"),
                        SideBar.NavItem(icon="book-key", text="Manage Secrets", href="/secrets-pki/secrets"),
                        SideBar.Header(title="PKI"),
                        SideBar.NavItem(
                            icon="gavel",
                            text="Certificate Authorities",
                            href="/secrets-pki/pki/certificate-authorities",
                        ),
                        SideBar.NavItem(
                            icon="shield-plus",
                            text="Intermediate CAs",
                            href="/secrets-pki/pki/intermediate-certificates",
                        ),
                        SideBar.NavItem(
                            icon="shield-check",
                            text="Leaf Certificates",
                            href="/secrets-pki/pki/leaf-certificates",
                        ),
                    ]
                ),
                SideBar.Section(icon="network", text="Sectors", href="/sectors"),
                SideBar.Section(icon="warehouse", text="DockFS", href="/dock-fs"),
                SideBar.Section(icon="database", text="DataCore", href="/datacore"),
                SideBar.Section(icon="chevrons-left-right-ellipsis", text="Conduit", href="/conduit"),
                SideBar.Section(icon="logs", text="Logs", href="/logs"),
            ),
            rx.el.div(
                page(),
                class_name=(
                    "w-full h-full flex-col p-4 overflow-auto "
                    "bg-gradient-to-b from-gray-200 to-gray-400 "
                    "dark:from-[#111317] dark:to-[#151820] "
                    "text-gray-800 dark:text-[#E8F1FF] "
                    "selection:bg-[#36E2F4]/40 selection:text-white "
                    "backdrop-blur-sm transition-colors duration-300 ease-in-out"
                ),
            ),
            class_name="h-screen w-full flex",
        )

    return wrapped
