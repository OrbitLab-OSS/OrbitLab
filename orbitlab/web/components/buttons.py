"""OrbitLab Button Components."""

from types import FunctionType, SimpleNamespace
from typing import TypedDict, Unpack

import reflex as rx


class PrimaryButtonProps(TypedDict, total=False):
    """Primary Button Component Props."""

    on_click: rx.EventHandler | rx.event.EventCallback | list[rx.EventHandler | rx.event.EventCallback]
    disabled: bool | rx.Var[bool]
    form: str


class PrimaryButton:
    """A primary button component with gradient styling and optional icon."""

    def __new__(cls, text: str, *, icon: str | None = None, **props: Unpack[PrimaryButtonProps]) -> rx.Component:
        """Create and return the primary button component."""
        class_name = props.pop("class_name", "")
        return rx.el.button(
            rx.icon(icon, size=16, class_name="mr-2") if icon else rx.fragment(),
            text,
            class_name=(
                "inline-flex items-center rounded-md px-3 py-2 text-sm font-semibold "
                "text-white bg-gradient-to-r from-[#1E63E9] to-[#36E2F4] "
                "hover:opacity-80 active:opacity-60 "
                "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:opacity-40 "
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#36E2F4]/40 "
                f"transition-all duration-200 shadow-md shadow-[#36E2F4]/30 {class_name}"
            ),
            **props, # pyright: ignore[reportArgumentType]
        )


class SecondaryButtonProps(TypedDict, total=False):
    """Secondary Button Component Props."""

    on_click: rx.EventHandler | rx.event.EventCallback | list[rx.EventHandler | rx.event.EventCallback]
    form: str


class SecondaryButton:
    """A secondary button component with subtle styling."""

    def __new__(cls, text: str, *, icon: str | None = None, **props: Unpack[SecondaryButtonProps]) -> rx.Component:
        """Create and return the secondary button component."""
        class_name = props.pop("class_name", "")
        return rx.el.button(
            rx.icon(icon, size=16, class_name="mr-2") if icon else rx.fragment(),
            text,
            class_name=(
                "inline-flex items-center rounded-md px-3 py-2 text-sm font-semibold "
                "text-gray-900 dark:text-[#E8F1FF] "
                "bg-gradient-to-b from-gray-300/50 to-gray-400/50 "
                "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:opacity-40 "
                "hover:bg-gray-200/20 active:bg-gray-200/50 "
                "backdrop-blur-sm shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)] "
                f"transition-all duration-200 {class_name}"
            ),
            **props, # pyright: ignore[reportArgumentType]
        )


class IconButtonProps(TypedDict, total=False):
    """Icon Button Component Props."""

    on_click: rx.EventHandler | rx.event.EventCallback | FunctionType | list[rx.EventHandler | rx.event.EventCallback]
    form: str
    size: int


class IconButton:
    """A button component that displays only an icon."""

    def __new__(cls, icon: str, **props: Unpack[IconButtonProps]) -> rx.Component:
        """Create and return the icon button component."""
        class_name = props.pop("class_name", "")
        return rx.el.button(
            rx.icon(icon, size=props.pop("size", 16)),
            class_name=(
                "p-3 rounded-full text-[rgb(0,150,255)] transition-all duration-200 ease-in-out "
                "hover:border hover:scale-105 hover:text-[rgb(0,200,255)] hover:bg-[rgba(0,150,255,0.1)] "
                "hover:border-[rgba(0,200,255,0.5)] hover:shadow-[0_0_6px_rgba(0,150,255,0.25)] cursor-pointer "
                f"{class_name}"
            ),
            **props, # pyright: ignore[reportArgumentType]
        )


class ButtonsNamespace(SimpleNamespace):
    """Button Components Namespace."""

    Primary = staticmethod(PrimaryButton)
    Secondary = staticmethod(SecondaryButton)
    Icon = staticmethod(IconButton)


Buttons = ButtonsNamespace()
