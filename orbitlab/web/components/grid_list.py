"""Grid list components for displaying items in a responsive grid layout."""

from types import SimpleNamespace
from typing import NotRequired, TypedDict, Unpack

import reflex as rx


class GridListItemProps(TypedDict, total=False):
    """GridListItem Props."""

    on_click: rx.event.EventCallback
    class_name: NotRequired[str]


class GridListItem:
    """A grid list item component that displays content with optional actions."""

    def __new__(
        cls,
        *children: rx.Component,
        actions: rx.Component | None = None,
        **props: Unpack[GridListItemProps],
    ) -> rx.Component:
        """Create a new grid list item component."""
        class_name = props.pop("class_name", "flex flex-1 flex-col justify-between p-8")
        if not actions:
            actions = rx.fragment()
        return rx.el.li(
            rx.el.div(
                *children,
                class_name=f"flex flex-1 flex-col justify-between p-8 {class_name}",
            ),
            actions,
            class_name=(
                "col-span-1 flex flex-col divide-y divide-white/10 text-center "
                "rounded-xl overflow-hidden border border-gray-200/50 dark:border-white/[0.08] "
                "bg-gradient-to-b from-gray-50/90 to-gray-200/60 "
                "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.08)] "
                "hover:ring-1 hover:ring-[#36E2F4]/30 "
                "hover:shadow-[0_0_10px_rgba(54,226,244,0.15)] "
                "transition-all duration-300 ease-in-out "
                "outline outline-1 outline-transparent -outline-offset-1"
            ),
            **props, # pyright: ignore[reportCallIssue]
        )


class GridListProps(TypedDict, total=False):
    """GridListRoot Props."""

    class_name: NotRequired[str]


class GridListRoot:
    """A root container component for grid list layouts."""

    def __new__(cls, *items: GridListItem | rx.Component, **props: Unpack[GridListProps]) -> rx.Component:
        """Create a new grid list root component."""
        class_name = props.pop("class_name", "")
        return rx.el.ul(
            *items,
            role=props.pop("role", "list"),
            class_name=(
                "grid grid-cols-1 gap-6 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 "
                f"{class_name}"
            ),
            **props, # pyright: ignore[reportCallIssue]
        )


class GridListNamespace(SimpleNamespace):
    """A namespace for GridList components providing root and item components."""

    __call__ = staticmethod(GridListRoot)
    Item = staticmethod(GridListItem)


GridList = GridListNamespace()
