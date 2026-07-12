"""Sidebar component module for the OrbitLab web application."""

import uuid
from types import SimpleNamespace

import reflex as rx
from pydantic import BaseModel, Field

from orbitlab.web.components.dialogs import ClusterSettingsDialog
from orbitlab.web import tailwind


class SideBarStatus(BaseModel):
    """Represents the state of a sidebar."""

    collapsed: bool = False
    show_settings_menu: bool = False


class SideBarStateManager(rx.State):
    """Manages the registration and toggle state of sidebars."""

    registered: rx.Field[dict[str, SideBarStatus]] = rx.field(default_factory=dict)

    @rx.var
    def current_path(self) -> str:
        """Get the current URL path from the router."""
        return self.router.url.path

    @rx.var
    def primary_uri(self) -> str:
        primary = next(iter([i for i in self.current_path.split("/") if i]), "")
        return f"/{primary}"

    @rx.event
    async def register(self, sidebar_id: str) -> None:
        """Register a sidebar by its identifier and set its state to False."""
        self.registered[sidebar_id] = SideBarStatus()

    @rx.event
    async def toggle(self, sidebar_id: str) -> None:
        """Toggle the expand/collapse state of the sidebar with the given sidebar_id."""
        self.registered[sidebar_id].collapsed = not self.registered[sidebar_id].collapsed

    @rx.event
    async def toggle_settings_menu(self, sidebar_id: str) -> None:
        """Toggle the state of the sidebar with the given sidebar_id."""
        self.registered[sidebar_id].show_settings_menu = not self.registered[sidebar_id].show_settings_menu


class SidebarNavItem(BaseModel):
    """A navigation item for the sidebar."""

    icon: str
    text: str
    href: str


class SidebarSectionHeader(BaseModel):
    """A section header for organizing navigation items in the sidebar."""

    title: str


class SidebarSection(SidebarNavItem):
    children: list[SidebarNavItem | SidebarSectionHeader] = Field(default_factory=list)


class SideBarRoot:
    """A collapsible sidebar component with navigation items and settings menu."""

    sidebar_id: str

    @classmethod
    def __section_header__(cls, header: SidebarSectionHeader, collapsed: rx.vars.BooleanVar) -> rx.Component:
        """Create a section header component for the sidebar."""
        return rx.el.div(
            rx.cond(
                collapsed,
                " •",
                header.title.upper(),
            ),
            data_collapsed=collapsed,
            class_name=(
                "px-3 pt-8 pb-1 text-base font-semibold tracking-wider uppercase "
                "text-[rgb(0,150,255)] dark:text-[rgb(0,200,255)] "
                "select-none opacity-80 text-center"
            ),
        )

    @classmethod
    def section_child(cls, item: SidebarNavItem | SidebarSectionHeader, collapsed: rx.vars.BooleanVar) -> rx.Component:
        if isinstance(item, SidebarNavItem):
            return rx.el.button(
                rx.el.div(
                    rx.icon(item.icon, size=20, class_name="transition-colors duration-200"),
                    rx.el.span(
                        item.text,
                        data_collapsed=collapsed,
                        class_name="text-sm font-medium transition-all duration-200 data-[collapsed=true]:hidden",
                    ),
                    class_name="flex items-center gap-3",
                ),
                on_click=rx.redirect(item.href),
                data_active=SideBarStateManager.current_path == item.href,
                data_collapsed=collapsed,
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
        return rx.el.div(
            rx.cond(
                collapsed,
                " •",
                item.title.upper(),
            ),
            data_collapsed=collapsed,
            class_name=(
                "px-3 not-first:pt-8 pb-1 text-base font-semibold tracking-wider uppercase "
                "text-[rgb(0,150,255)] dark:text-[rgb(0,200,255)] "
                "select-none opacity-80 text-center"
            ),
        )

    @classmethod
    def section(cls, section: SidebarSection, collapsed: rx.vars.BooleanVar) -> rx.Component:
        """Create a navigation item button for the sidebar."""
        return rx.el.div(
            rx.el.button(
                rx.el.div(
                    rx.icon(section.icon, size=20, class_name="transition-colors duration-200"),
                    rx.el.span(
                        section.text,
                        data_collapsed=collapsed,
                        class_name="text-sm font-medium transition-all duration-200 data-[collapsed=true]:hidden",
                    ),
                    class_name="flex items-center gap-3",
                ),
                on_click=rx.redirect(section.href),
                data_active=SideBarStateManager.current_path == section.href,
                data_collapsed=collapsed,
                class_name=(
                    "flex items-start w-full px-3 py-2.5 rounded-lg data-[active=true]:bg-sky-100 "
                    "data-[active=true]:text-sky-600 data-[active=true]:dark:bg-sky-900/50 "
                    "data-[active=true]:dark:text-sky-300 data-[active=false]:text-gray-500 "
                    "data-[active=false]:dark:text-gray-400 "
                    "data-[active=false]:hover:bg-gray-100 data-[active=false]:dark:hover:bg-gray-800 "
                    "data-[active=false]:hover:text-gray-800 data-[active=false]:dark:hover:text-gray-200 "
                    "data-[collapsed=true]:justify-center"
                ),
            ),
            rx.el.div(
                *[
                    cls.section_child(item=item, collapsed=collapsed)
                    for item in section.children
                ],
                data_active=SideBarStateManager.primary_uri == section.href,
                data_children=len(section.children) > 0,
                class_name=(
                    "flex flex-col gap-1 mt-1 py-2 rounded-lg "
                    "bg-gray-100/60 dark:bg-white/[0.03] "
                    "border-l border-gray-200 dark:border-white/[0.08] "
                    "data-[active=false]:hidden data-[children=false]:hidden"
                ),
            ),
        )
        

    def __new__(cls, *sections: SidebarSection) -> rx.Component:
        """Create a new sidebar component instance."""
        cls.sidebar_id = str(uuid.uuid4())
        collapsed = SideBarStateManager.registered.get(cls.sidebar_id, {}).to(dict).get("collapsed", False).to(bool)
        return rx.el.aside(
            rx.el.div(
                rx.el.div(
                    rx.el.div(
                        rx.el.a(
                            tailwind.OrbitLabLogo(),
                            rx.el.span(
                                "OrbitLab",
                                data_collapsed=collapsed,
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
                            data_collapsed=collapsed,
                            class_name=(
                                "p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 "
                                "data-[collapsed=true]:rotate-180"
                            ),
                            style={"transition": "transform 0.3s ease-in-out"},
                        ),
                        data_collapsed=collapsed,
                        class_name="flex items-center justify-between p-3 data-[collapsed=true]:flex-col",
                    ),
                    rx.el.nav(
                        *[cls.section(section=section, collapsed=collapsed) for section in sections],
                        class_name="flex flex-col gap-1 p-2",
                    ),
                ),
                rx.el.div(
                    tailwind.Menu(
                        rx.el.button(
                            rx.el.div(
                                rx.icon("settings", size=20),
                                rx.el.span(
                                    "Settings",
                                    data_collapsed=collapsed,
                                    class_name="text-sm font-medium data-[collapsed=true]:hidden",
                                ),
                                class_name="flex items-center gap-3",
                            ),
                            data_collapsed=collapsed,
                            class_name=(
                                "flex items-start w-full px-3 py-2.5 rounded-lg text-gray-500 dark:text-gray-400 "
                                "hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-800 "
                                "dark:hover:text-gray-200 data-[collapsed=true]:justify-center"
                            ),
                        ),
                        tailwind.Menu.Item(
                            rx.text("Cluster Settings"),
                            on_click=ClusterSettingsDialog.open,
                        ),
                        tailwind.Menu.Separator(),
                        rx.color_mode_cond(
                            dark=tailwind.Menu.Item(
                                rx.el.div(
                                    rx.icon("sun", size=12, class_name="text-amber-500"),
                                    rx.text("Light Mode"),
                                    class_name="flex space-x-4 items-center justify-between",
                                ),
                                on_click=rx.toggle_color_mode,  # pyright: ignore[reportArgumentType]
                            ),
                            light=tailwind.Menu.Item(
                                rx.el.div(
                                    rx.icon("moon", size=12, class_name="text-[#1E63E9]"),
                                    rx.text("Dark Mode"),
                                    class_name="flex space-x-4 items-center justify-between",
                                ),
                                on_click=rx.toggle_color_mode,  # pyright: ignore[reportArgumentType]
                            ),
                        ),
                        data_collapsed=collapsed,
                    ),
                    class_name="p-2",
                ),
                class_name="flex flex-col justify-between h-full",
            ),
            ClusterSettingsDialog(),
            data_collapsed=collapsed,
            on_mount=SideBarStateManager.register(cls.sidebar_id),
            class_name=(
                "h-screen flex flex-col justify-between "
                "border-r border-gray-200 dark:border-white/[0.08] "
                "transition-all duration-300 ease-in-out "
                "w-64 data-[collapsed=true]:w-14 "
                "bg-gradient-to-b from-gray-50/95 to-gray-200/80 "
                "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)] "
                "hover:ring-1 hover:ring-[#36E2F4]/30"
            ),
        )


class SideBarNamespace(SimpleNamespace):
    """A namespace for sidebar-related components and utilities."""

    __call__ = staticmethod(SideBarRoot)
    Section = staticmethod(SidebarSection)
    Header = staticmethod(SidebarSectionHeader)
    NavItem = staticmethod(SidebarNavItem)


SideBar = SideBarNamespace()
