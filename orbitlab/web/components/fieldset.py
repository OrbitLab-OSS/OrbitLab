"""OrbitLab FieldSet Component."""

import reflex as rx


class FieldItem:
    """A field component that combines a label with another component."""

    def __new__(cls, label: str, component: rx.Component) -> rx.Component:
        """Create a field with a label and component."""
        return rx.el.div(
            rx.el.p(
                label,
                class_name="w-1/4 mr-4 text-base font-semibold text-gray-900 dark:text-[#E8F1FF]",
            ),
            component,
            class_name="w-full flex items-center",
        )


class FieldSet:
    """A fieldset component that groups related form fields with a title and styled border."""

    Field = staticmethod(FieldItem)

    def __new__(cls, title: str, *children: rx.Component) -> rx.Component:
        """Create and return the fieldset component."""
        return rx.el.fieldset(
            rx.el.legend(
                title,
                class_name=(
                    "text-sm font-semibold tracking-wide uppercase "
                    "text-gray-800 dark:text-[#E8F1FF] "
                    "px-3 -ml-1 "
                    "rounded-md "
                    "relative "
                    "top-[-0.6rem] "
                    "bg-gradient-to-r from-white/90 to-gray-100/70 "
                    "dark:from-[#0E1015]/90 dark:to-[#181B22]/90 "
                    "border border-gray-200 dark:border-white/[0.08] "
                    "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.08)] "
                    "hover:ring-1 hover:ring-[#36E2F4]/30 "
                    "transition-all duration-300 ease-in-out "
                    "backdrop-blur-sm "
                ),
            ),
            *children,
            class_name=(
                "relative p-4 mt-4 mb-6 "
                "rounded-xl flex flex-col space-y-2 "
                "border border-gray-200 dark:border-white/[0.08] "
                "bg-gradient-to-b from-white/90 to-gray-100/70 "
                "dark:from-[#0E1015]/80 dark:to-[#181B22]/80 "
                "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)] "
                "hover:ring-1 hover:ring-[#36E2F4]/30 "
                "transition-all duration-300 ease-in-out "
                "backdrop-blur-sm"
            ),
        )
