"""OrbitLab HoverCard Component."""

import reflex as rx


class HoverCard:
    """OrbitLab-themed hover card component with soft chrome styling and accent glow."""

    def __new__(cls, trigger: rx.Component, *content: rx.Component) -> rx.Component:
        """Create and return the hover card component."""
        return rx.hover_card.root(
            rx.hover_card.trigger(
                trigger,
                class_name=(
                    "cursor-pointer transition-all duration-200 ease-in-out "
                    "text-gray-700 dark:text-gray-300 "
                    "hover:text-[#1E63E9] dark:hover:text-[#36E2F4] "
                    "hover:drop-shadow-[0_0_4px_rgba(54,226,244,0.4)]"
                ),
            ),
            rx.hover_card.content(
                *content,
                side="top",
                align="center",
                class_name=(
                    "max-w-xs px-4 py-3 rounded-lg shadow-lg "
                    "border border-gray-200 dark:border-white/[0.08] "
                    "backdrop-blur-sm select-none "
                    "bg-gradient-to-b from-white/95 to-gray-100/80 "
                    "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                    "ring-1 ring-transparent hover:ring-[#36E2F4]/40 "
                    "hover:shadow-[0_0_10px_rgba(54,226,244,0.25)] "
                    "transition-all duration-200 ease-in-out "
                    "text-gray-800 dark:text-[#E8F1FF]"
                ),
            ),
        )
