"""OrbitLab Popover Component."""

from typing import Literal, TypedDict, Unpack

import reflex as rx


class PopoverProps(TypedDict, total=False):
    """Popover Component Props."""

    size: Literal["1", "2", "3", "4"]
    side: Literal["top", "right", "bottom", "left"]
    side_offset: int


class Popover:
    """A popover component for displaying content in an overlay."""

    def __new__(cls, trigger: rx.Component, *children: rx.Component, **props: Unpack[PopoverProps]) -> rx.Component:
        """Create and return the popover component."""
        props.setdefault("size", "1")
        props.setdefault("side", "bottom")
        props.setdefault("side_offset", 10)
        class_name = props.pop("class_name", "")
        return rx.popover.root(
            rx.popover.trigger(
                trigger,
                class_name=(
                    "w-fit px-3 py-1.5 rounded-lg text-sm font-medium "
                    "bg-gradient-to-b from-gray-50/95 to-gray-200/80 text-gray-800 "
                    "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 dark:text-gray-100 "
                    "border border-gray-200 dark:border-white/[0.08] "
                    "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)] "
                    "hover:ring-1 hover:ring-[#36E2F4]/30 "
                    "transition-all duration-300"
                ),
            ),
            rx.popover.content(
                *children,
                class_name=(
                    "rounded-xl p-4 z-50 "
                    "bg-gradient-to-b from-white/95 to-gray-100/80 "
                    "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                    "border border-gray-200 dark:border-white/[0.08] "
                    "outline outline-1 outline-gray-200/50 dark:outline-white/[0.06] "
                    "shadow-xl shadow-black/5 dark:shadow-black/30 "
                    "backdrop-blur-md "
                    "data-[state=open]:animate-fade-in data-[state=closed]:animate-fade-out "
                    f"transition-all duration-200 {class_name}"
                ),
                **props,
            ),
        )
