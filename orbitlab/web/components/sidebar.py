"""Sidebar component module for the OrbitLab web application."""

import uuid
from types import SimpleNamespace
from typing import TypedDict

import reflex as rx
from pydantic import BaseModel

from orbitlab.web.components.logo import OrbitLabLogo


class SideBarStatus(BaseModel):
    """Represents the state of a sidebar.

    Attributes:
        active_page (str): The currently active page in the sidebar.
        collapsed (bool): Whether the sidebar is collapsed. Defaults to False.
        show_settings_menu (bool): Whether the settings menu is shown. Defaults to False.
    """

    active_page: str = ""
    collapsed: bool = False
    show_settings_menu: bool = False


class SideBarStateManager(rx.State):
    """Manages the registration and toggle state of sidebars.

    Attributes:
        registered (dict[str, SideBarStatus]): A dictionary mapping sidebar identifiers to their open/closed state.
    """

    registered: dict[str, SideBarStatus] = rx.field(default_factory=dict)

    @rx.var
    def current_path(self) -> str:
        """Get the current URL path from the router."""
        return self.router.url.path

    @rx.event
    async def register(self, sidebar_id: str) -> None:
        """Register a sidebar by its identifier and set its state to False.

        Parameters:
            sidebar_id (str): The identifier of the sidebar to register.
        """
        self.registered[sidebar_id] = SideBarStatus()

    @rx.event
    async def toggle(self, sidebar_id: str) -> None:
        """Toggle the expand/collapse state of the sidebar with the given sidebar_id."""
        self.registered[sidebar_id].collapsed = not self.registered[sidebar_id].collapsed

    @rx.event
    async def toggle_settings_menu(self, sidebar_id: str) -> None:
        """Toggle the state of the sidebar with the given sidebar_id.

        Parameters:
            sidebar_id (str): The identifier of the sidebar to toggle.
        """
        self.registered[sidebar_id].show_settings_menu = not self.registered[sidebar_id].show_settings_menu


class NavItem(TypedDict):
    """A navigation item for the sidebar."""

    icon: str
    text: str
    href: str


class SectionHeader(TypedDict):
    """A section header for organizing navigation items in the sidebar.

    Attributes:
        title (str): The title text to display for the section header.
    """
    title: str


class SideBarRoot:
    """A collapsible sidebar component with navigation items and settings menu."""

    sidebar_id: str

    @classmethod
    def __settings_menu__(cls) -> rx.Component:
        """Create the settings menu component for the sidebar.

        Returns:
            A component containing the settings menu with cluster settings, administration, and dark mode toggle.
        """
        return rx.el.div(
            rx.el.div(
                rx.el.button(
                    "Cluster Settings",
                    class_name=(
                        "w-full text-left px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 "
                        "dark:hover:bg-gray-700 rounded-md"
                    ),
                ),
                rx.el.button(
                    "Administration",
                    class_name=(
                        "w-full text-left px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 "
                        "dark:hover:bg-gray-700 rounded-md"
                    ),
                ),
                rx.el.div(class_name="my-1 h-px bg-gray-200 dark:bg-gray-700"),
                rx.el.div(
                    rx.el.span(
                        "Dark Mode",
                        class_name="text-sm text-gray-700 dark:text-gray-300",
                    ),
                    rx.el.button(
                        rx.el.span(
                            rx.icon("sun", size=12, class_name="text-yellow-500"),
                            rx.icon("moon", size=12, class_name="text-white"),
                            class_name=(
                                "flex items-center justify-start dark:justify-end h-4 w-9 rounded-full bg-gray-200 "
                                "dark:bg-sky-500 transition-all duration-300"
                            ),
                        ),
                        on_click=rx.toggle_color_mode,
                        class_name="p-0.5",
                    ),
                    class_name="flex items-center justify-between px-3 py-2",
                ),
                data_active=SideBarStateManager.registered.get(cls.sidebar_id).show_settings_menu,
                class_name=(
                    "fixed bottom-10 left-2 z-100 mb-3 p-2 bg-white dark:bg-gray-800 border border-gray-200 "
                    "dark:border-gray-700 rounded-xl shadow-lg data-[active=false]:hidden"
                ),
            ),
            rx.el.button(
                rx.el.div(
                    rx.icon("settings", size=20),
                    rx.el.span(
                        "Settings",
                        data_collapsed=SideBarStateManager.registered.get(cls.sidebar_id).collapsed,
                        class_name="text-sm font-medium data-[collapsed=true]:hidden",
                    ),
                    class_name="flex items-center gap-3",
                ),
                on_click=lambda: SideBarStateManager.toggle_settings_menu(cls.sidebar_id),
                data_collapsed=SideBarStateManager.registered.get(cls.sidebar_id).collapsed,
                class_name=(
                    "flex items-start w-full px-3 py-2.5 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 "
                    "dark:hover:bg-gray-800 hover:text-gray-800 dark:hover:text-gray-200 "
                    "data-[collapsed=true]:justify-center"
                ),
            ),
            class_name="relative",
        )

    @classmethod
    def __section_header__(cls, header: SectionHeader) -> rx.Component:
        """Create a section header component for the sidebar.

        Args:
            header: The section header configuration containing the title.

        Returns:
            A component representing the section header.
        """
        return rx.el.div(
            rx.cond(
                SideBarStateManager.registered.get(cls.sidebar_id).collapsed,
                " •",
                header["title"].upper(),
            ),
            data_collapsed=SideBarStateManager.registered.get(cls.sidebar_id).collapsed,
            class_name=(
                "px-3 pt-4 pb-1 text-xs font-semibold tracking-wider uppercase "
                "text-gray-500 dark:text-gray-400 "
                "select-none opacity-80 data-[collapsed=true]:text-center"
            ),
        )

    @classmethod
    def __nav_item__(cls, nav_item: NavItem) -> rx.Component:
        """Create a navigation item button for the sidebar.

        Args:
            nav_item: The navigation item configuration containing icon and text.

        Returns:
            A button component representing the navigation item.
        """
        return rx.el.button(
            rx.el.div(
                rx.icon(nav_item["icon"], size=20, class_name="transition-colors duration-200"),
                rx.el.span(
                    nav_item["text"],
                    data_collapsed=SideBarStateManager.registered.get(cls.sidebar_id).collapsed,
                    class_name="text-sm font-medium transition-all duration-200 data-[collapsed=true]:hidden",
                ),
                class_name="flex items-center gap-3",
            ),
            on_click=rx.redirect(nav_item["href"]),
            data_active=SideBarStateManager.current_path == nav_item["href"],
            data_collapsed=SideBarStateManager.registered.get(cls.sidebar_id).collapsed,
            class_name=(
                "flex items-start w-full px-3 py-2.5 rounded-lg data-[active=true]:bg-sky-100 "
                "data-[active=true]:text-sky-600 data-[active=true]:dark:bg-sky-900/50 "
                "data-[active=true]:dark:text-sky-300 data-[active=false]:text-gray-500 "
                "data-[active=false]:dark:text-gray-400 "
                "data-[active=false]:hover:bg-gray-100 data-[active=false]:dark:hover:bg-gray-800 "
                "data-[active=false]:hover:text-gray-800 data-[active=false]:dark:hover:text-gray-200 "
                "data-[collapsed=true]:justify-center"
            ),
        )

    def __new__(
        cls,
        *nav_items: NavItem | SectionHeader,
        title: str = "OrbitLab",
    ) -> tuple[rx.Component, str]:
        """Create a new sidebar component instance.

        Parameters:
            nav_items: A sequence of navigation items to display in the sidebar.
            title: The sidebar Title.

        Returns:
            A Reflex component representing the complete sidebar and its ID.

        Raises:
            RuntimeError: If the default_page is not found in the nav_items.
        """
        cls.sidebar_id = str(uuid.uuid4())
        return rx.el.aside(
            rx.el.div(
                rx.el.div(
                    rx.el.div(
                        rx.el.a(
                            OrbitLabLogo(),
                            rx.el.span(
                                title,
                                data_collapsed=SideBarStateManager.registered.get(cls.sidebar_id).collapsed,
                                class_name=(
                                    "text-lg font-bold text-nowrap text-gray-800 dark:text-gray-100 "
                                    "data-[collapsed=true]:hidden"
                                ),
                            ),
                            href="/",
                            class_name="flex items-center gap-3 cursor-pointer",
                        ),
                        rx.el.button(
                            rx.icon(
                                "chevrons-left",
                                size=20,
                                class_name="text-gray-500 dark:text-gray-400",
                            ),
                            on_click=lambda: SideBarStateManager.toggle(cls.sidebar_id),
                            data_collapsed=SideBarStateManager.registered.get(cls.sidebar_id).collapsed,
                            class_name=(
                                "p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 "
                                "data-[collapsed=true]:rotate-180"
                            ),
                            style={"transition": "transform 0.3s ease-in-out"},
                        ),
                        data_collapsed=SideBarStateManager.registered.get(cls.sidebar_id).collapsed,
                        class_name="flex items-center justify-between p-3 data-[collapsed=true]:flex-col",
                    ),
                    rx.el.nav(
                        *[
                            cls.__section_header__(item) if "title" in item else cls.__nav_item__(item)
                            for item in nav_items
                        ],
                        class_name="flex flex-col gap-1 p-2",
                    ),
                ),
                rx.el.div(cls.__settings_menu__(), class_name="p-2"),
                class_name="flex flex-col justify-between h-full",
            ),
            data_collapsed=SideBarStateManager.registered.get(cls.sidebar_id).collapsed,
            on_mount=SideBarStateManager.register(cls.sidebar_id),
            class_name=(
                "h-screen flex flex-col justify-between "
                "border-r border-gray-200 dark:border-white/[0.08] "
                "transition-all duration-300 ease-in-out "
                "w-64 data-[collapsed=true]:w-14 "
                # === Light mode chrome ===
                "bg-gradient-to-b from-gray-50/95 to-gray-200/80 "
                # === Dark mode chrome ===
                "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)] "
                "hover:ring-1 hover:ring-[#36E2F4]/30"
            ),
        )


class SideBarNamespace(SimpleNamespace):
    """A namespace for sidebar-related components and utilities.

    Attributes:
        __call__: The main SideBarRoot component factory.
        NavItem: TypedDict for navigation item structure.
        Manager: State manager for sidebar registration and control.
    """

    __call__ = staticmethod(SideBarRoot)
    SectionHeader = staticmethod(SectionHeader)
    NavItem = staticmethod(NavItem)
    Manager = SideBarStateManager


SideBar = SideBarNamespace()
