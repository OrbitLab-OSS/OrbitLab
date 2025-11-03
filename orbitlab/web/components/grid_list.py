"""Grid list components for displaying items in a responsive grid layout."""
from types import SimpleNamespace

import reflex as rx


class GridListItem:
    """A grid list item component that displays content with optional actions.

    This class creates individual items for use within a GridList, featuring a content area
    for child components and an optional actions section.
    """
    def __new__(cls, *children: rx.Component, actions: rx.Component | None = None) -> rx.Component:
        """Create a new grid list item component.

        Args:
            *children: Variable number of child components to display in the item content area.
            actions: Optional component to display in the actions area of the item.

        Returns:
            A Reflex component representing a grid list item.
        """
        if not actions:
            actions = rx.fragment()
        return rx.el.li(
            rx.el.div(
                *children,
                class_name="flex flex-1 flex-col justify-between p-8",
            ),
            actions,
            class_name=(
                # Layout + Structure
                "col-span-1 flex flex-col divide-y divide-white/10 text-center "
                "rounded-xl overflow-hidden border border-gray-200/50 dark:border-white/[0.08] "
                # Background gradient (chrome look)
                "bg-gradient-to-b from-gray-50/90 to-gray-200/60 "
                "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                # Subtle metallic polish + hover glow
                "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.08)] "
                "hover:ring-1 hover:ring-[#36E2F4]/30 "
                "hover:shadow-[0_0_10px_rgba(54,226,244,0.15)] "
                # Motion & feel
                "transition-all duration-300 ease-in-out "
                "outline outline-1 outline-transparent -outline-offset-1 "
            ),
        )


class GridListRoot:
    """A root container component for grid list layouts.

    Creates a responsive grid layout that displays GridListItem components in a grid pattern
    that adapts from 1 column on mobile to 4 columns on large screens.
    """
    def __new__(cls, *items: GridListItem, **props: dict) -> rx.Component:
        """Create a new grid list root component.

        Args:
            *items: Variable number of GridListItem components to display in the grid.
            **props: Additional properties to pass to the underlying ul element.

        Returns:
            A Reflex component representing the grid list container.
        """
        return rx.el.ul(
            *items,
            role=props.pop("role", "list"),
            class_name=(
                f"grid grid-cols-1 gap-6 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 {props.pop('class_name', '')}"
            ),
            **props,
        )


class GridListNamespace(SimpleNamespace):
    """A namespace for GridList components providing root and item components.

    This class creates a callable namespace that acts as both a constructor for the grid list
    and a container for the GridListItem component.

    Attributes:
        __call__ (GridListRoot): Callable that creates the root grid list component.
        Item (GridListItem):  Component class for individual grid list items.
    """
    __call__ = staticmethod(GridListRoot)
    Item = staticmethod(GridListItem)


GridList = GridListNamespace()
