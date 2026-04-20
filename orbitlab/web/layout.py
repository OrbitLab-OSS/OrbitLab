"""OrbitLab Layout."""

from collections.abc import Callable

import reflex as rx

from orbitlab.data_types import InitializationStatus
# from orbitlab.web.tailwind.initializer import InitializationState
from orbitlab.web.tailwind.sidebar import SideBar


def require_configuration(page: Callable[[], rx.Component]) -> Callable[[], rx.Component]:
    """Decorator to require that the configuration is complete before rendering the page."""

    def wrapped() -> rx.Component:
        return rx.cond(
            # InitializationState.status == InitializationStatus.COMPLETE,
            True,
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
                    icon="server-cog",
                    children=[
                        SideBar.Header(title="LXC"),
                        SideBar.NavItem(icon="cpu", text="Instances", href="/compute/lxc/instances"),
                        SideBar.NavItem(icon="file-box", text="Appliances", href="/compute/lxc/appliances"),
                        SideBar.Header(title="VM"),
                        SideBar.NavItem(icon="cpu", text="Instances", href="/compute/vm/instances"),
                        SideBar.NavItem(icon="hard-drive", text="Images", href="/compute/vm/images"),
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
                SideBar.Section(icon="logs", text="Logs", href="/logs"),
            ),
            rx.el.div(
                page(),
                class_name=(
                    "h-full w-full flex-col p-4 "
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
