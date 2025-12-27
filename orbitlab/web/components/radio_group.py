"""OrbitLab Radio Group Component."""

from enum import Enum
from typing import TypedDict, Unpack

import reflex as rx

from orbitlab.data_types import FrontendEvents


class RadioItemProps(TypedDict, total=False):
    """Radio Item component props."""

    on_change: FrontendEvents
    value: str | Enum | rx.Var[str | Enum]
    class_name: str


class RadioItem:
    """A class representing a single radio button item component."""

    def __new__(cls, item: str, label: str | None = None, **props: Unpack[RadioItemProps]) -> rx.Component:
        """Create and return the radio item component."""
        class_name = props.pop("class_name", "")
        value = props.pop("value", None)
        return rx.el.label(
            rx.el.input(
                type="radio",
                id=item,
                class_name="peer sr-only",
                checked=value == item,
                **props, # pyright: ignore[reportCallIssue]
            ),
            rx.el.span(
                rx.el.span(label or item.title(), class_name="truncate"),
                class_name=(
                    "inline-flex items-center justify-center px-4 py-2 rounded-lg text-sm font-medium "
                    "transition-all duration-200 select-none "
                    "text-gray-800 dark:text-gray-200 "
                    "bg-gradient-to-b from-gray-50/95 to-gray-200/70 "
                    "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                    "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)] "
                    "border border-gray-200 dark:border-white/[0.08] "
                    "hover:ring-1 hover:ring-[#36E2F4]/35 "
                    "focus:outline-none focus-visible:ring-2 focus-visible:ring-[#36E2F4]/40 "
                    "peer-checked:text-[#1E63E9] dark:peer-checked:text-[#36E2F4] "
                    "peer-checked:bg-[#1E63E9]/10 dark:peer-checked:bg-[#36E2F4]/10 "
                    "peer-checked:border-[#1E63E9]/40 dark:peer-checked:border-[#36E2F4]/40 "
                    "peer-checked:shadow-[0_0_10px_rgba(54,226,244,0.15)] "
                    f"peer-disabled:opacity-40 peer-disabled:cursor-not-allowed {class_name}"
                ),
                aria_hidden="true",
            ),
            html_for=item,
            class_name="cursor-pointer",
        )


class RadioProps(TypedDict, total=False):
    """Radio component props."""

    class_name: str


class RadioGroup:
    """A group component for rendering a set of radio button items."""

    Item = staticmethod(RadioItem)

    def __new__(cls, *children: rx.Component, **props: Unpack[RadioProps]) -> rx.Component:
        """Create and return the radio group."""
        _ = props.pop("role", None)
        class_name = props.pop("class_name", "")
        return rx.el.div(
            *children,
            class_name=f"flex flex-row items-center gap-3 p-2 {class_name}",
            role="radiogroup",
            **props, # pyright: ignore[reportCallIssue]
        )
