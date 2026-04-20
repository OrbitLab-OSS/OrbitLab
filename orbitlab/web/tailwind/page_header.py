"""OrbitLab Page Header Component."""

import reflex as rx


class PageHeader:
    """A page header component with title and action buttons."""

    def __new__(cls, header: str, *actions: rx.Component) -> rx.Component:
        """Create and return the page header component."""
        return rx.el.div(
            rx.el.div(
                rx.el.h2(
                    header,
                    class_name=("truncate text-2xl font-bold tracking-tight text-gray-900 dark:text-[#E8F1FF]"),
                ),
                class_name="min-w-0 flex-1",
            ),
            rx.el.div(
                *actions,
                class_name="mt-2 flex space-x-2 lg:mt-4 lg:mr-4",
            ),
            class_name="flex not-lg:flex-col md:justify-start lg:flex-row lg:items-center lg:justify-between",
        )
