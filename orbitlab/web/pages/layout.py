"""OrbitLab Default Layout."""

import reflex as rx


class DefaultLayout:
    """Default layout for all OrbitLab Pages."""

    def __new__(cls, side_bar: rx.Component, *children: rx.Component) -> rx.Component:
        """Create and return the default layout."""
        return rx.el.div(
            side_bar,
            rx.el.div(
                *children,
                class_name=(
                    "min-h-screen w-full flex flex-col p-4 "
                    "bg-gradient-to-b from-gray-200 to-gray-400 "
                    "dark:from-[#111317] dark:to-[#151820] "
                    "text-gray-800 dark:text-[#E8F1FF] "
                    "selection:bg-[#36E2F4]/40 selection:text-white "
                    "backdrop-blur-sm transition-colors duration-300 ease-in-out"
                ),
            ),
            class_name="min-h-screen w-full flex",
        )
