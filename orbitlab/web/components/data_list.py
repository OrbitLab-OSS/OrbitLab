"""Data List Component."""

import reflex as rx


class DataListLabel:
    """Data List Label."""

    def __new__(cls, *children: rx.Component | str) -> rx.Component:
        """Create and return the label."""
        return rx.el.dt(
            *children,
            class_name=(
                "text-sm font-medium "
                "text-gray-600 dark:text-[#AEB9CC] "
                "whitespace-nowrap"
            ),
        )


class DataListValue:
    """Data List Value."""

    def __new__(cls, *children: rx.Component | str | rx.Var[str]) -> rx.Component:
        """Create and return the value."""
        return rx.el.dd(
            *children,
            class_name=(
                "text-sm text-gray-900 dark:text-[#E8F1FF] "
                "ml-4 flex-1 text-right"
            ),
        )


class DataListItem:
    """Data List Item consisting of a Label and a Value."""

    def __new__(cls, label: rx.Component, value: rx.Component) -> rx.Component:
        """Create and return the item."""
        return rx.el.div(
            label,
            value,
            class_name=(
                "px-4 py-2.5 "
                "flex items-center justify-between gap-4 "
                "border-b border-gray-200/70 dark:border-white/[0.06] "
                "hover:bg-gray-50/50 dark:hover:bg-white/[0.04] "
                "transition-colors duration-150"
            ),
        )


class DataList:
    """Data List Component.

    A styled data list component with nested classes for items, labels, and values.
    Provides a clean interface for displaying key-value pairs in a structured format.
    """
    Item = staticmethod(DataListItem)
    Label = staticmethod(DataListLabel)
    Value = staticmethod(DataListValue)

    def __new__(cls, *items: rx.Component, **props: dict) -> rx.Component:
        """Create and return the data list."""
        class_name = props.pop("class_name", "")
        return rx.el.div(
            rx.el.dl(
                *items,
                class_name=(
                    "divide-y divide-gray-200 dark:divide-white/[0.08] "
                    "bg-gradient-to-b from-white/90 to-gray-100/70 "
                    "dark:from-[#0E1015]/80 dark:to-[#12141A]/80 "
                    "backdrop-blur-sm"
                ),
            ),
            class_name=(
                "rounded-xl overflow-hidden "
                "outline outline-1 outline-gray-200 dark:outline-white/[0.08] "
                "shadow-md hover:shadow-lg transition-shadow duration-300 "
                f"{class_name}"
            ),
        )
