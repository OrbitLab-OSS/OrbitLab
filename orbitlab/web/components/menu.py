"""OrbitLab Dropdown Menu Component."""

from typing import NotRequired, TypedDict, Unpack

import reflex as rx

from orbitlab.data_types import FrontendEvents


class ItemProps(TypedDict, total=False):
    """Type definition for optional menu item component properties."""
    on_click: FrontendEvents
    class_name: NotRequired[str]
    danger: bool


class MenuItem:
    """A dropdown menu item component with hover effects and styling."""

    def __new__(cls, child: str | rx.Component, **props: Unpack[ItemProps]) -> rx.Component:
        """Create and return the menu item component."""
        danger = props.pop("danger", False)
        props["class_name"] = (
            "p-3 rounded-full text-[rgb(0,150,255)] transition-all duration-200 ease-in-out "
            "hover:border hover:scale-105 hover:text-[rgb(0,200,255)] hover:bg-[rgba(0,150,255,0.1)] "
            "hover:border-[rgba(0,200,255,0.5)] hover:shadow-[0_0_6px_rgba(0,150,255,0.25)] cursor-pointer "
            "data-[danger=true]:text-[#DC2626] data-[danger=true]:hover:border-[#DC2626]/50 "
            "data-[danger=true]:hover:bg-[#DC2626]/20 "
            f"{props.get('class_name', '')}"
        )
        return rx.dropdown_menu.item(child, data_danger=danger, **props) # pyright: ignore[reportArgumentType]


class Props(TypedDict, total=False):
    """Type definition for optional menu item component properties."""
    class_name: str
    data_collapsed: rx.Var[bool]


class Menu:
    """A dropdown menu component with items and separators."""

    Item = staticmethod(MenuItem)
    Separator = staticmethod(rx.dropdown_menu.separator)

    def __new__(cls, trigger: rx.Component, *children: rx.Component, **props: Unpack[Props]) -> rx.Component:
        """Create and return the menu component."""
        return rx.dropdown_menu.root(
            rx.dropdown_menu.trigger(trigger),
            rx.dropdown_menu.content(*children),
            **props,
        )
