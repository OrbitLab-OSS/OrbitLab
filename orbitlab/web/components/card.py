"""Card component factory module for creating styled card UI elements."""

from types import SimpleNamespace

import reflex as rx


class CardHeader:
    """A factory class for creating card header components."""

    def __new__(cls, *children: rx.Component) -> rx.Component:
        """Create a card header component.

        Args:
            *children: Child components to render inside the header.

        Returns:
            A div element styled as a card header.
        """
        return rx.el.div(
            *children,
            class_name=(
                "px-4 py-5 sm:px-6 "
                "bg-gradient-to-b from-white/90 to-gray-50/80 "
                "text-gray-900 "
                "dark:from-[#14171D]/95 dark:to-[#191C23]/95 "
                "dark:text-[#E8F1FF] "
                "border-b border-gray-200 dark:border-white/[0.08] "
                "backdrop-blur-sm "
                "font-medium tracking-wide "
                "shadow-[inset_0_-1px_0_rgba(255,255,255,0.05)]"
            ),
        )


class CardFooter:
    """A factory class for creating card footer components."""

    def __new__(cls, *children: rx.Component) -> rx.Component:
        """Create a card footer component.

        Args:
            *children: Child components to render inside the footer.

        Returns:
            A div element styled as a card footer.
        """
        return rx.el.div(
            *children,
            class_name=(
                "px-4 py-4 sm:px-6 "
                "bg-gradient-to-t from-gray-50/90 to-white/80 "
                "text-gray-700 "
                "dark:from-[#12141A]/95 dark:to-[#0E1015]/90 "
                "dark:text-gray-400 "
                "border-t border-gray-200 dark:border-white/[0.08] "
                "backdrop-blur-sm "
                "shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] "
                "transition-colors duration-300 ease-in-out"
            ),
        )


class CardRoot:
    """A factory class for creating card root components."""

    def __new__(
        cls,
        *children: rx.Component,
        header: rx.Component | None = None,
        footer: rx.Component | None = None,
        class_name: str = "",
    ) -> rx.Component:
        """Create a card root component with optional header and footer.

        Args:
            *children: Child components to render inside the card body.
            header: Optional header component for the card.
            footer: Optional footer component for the card.
            class_name: The tailwind class.

        Returns:
            A div element styled as a card container.
        """
        return rx.el.div(
            header,
            rx.el.div(
                *children,
                class_name=(
                    "divide-y divide-gray-200 dark:divide-white/10 "
                    "outline outline-1 outline-gray-200 dark:outline-white/10 "
                    "shadow-md hover:shadow-lg transition-shadow duration-300 "
                    "backdrop-blur-sm "
                    "bg-gradient-to-b from-white/90 to-gray-100/80 "
                    "dark:bg-gray-800/40 dark:from-[#0E1015]/80 dark:to-[#12141A]/90"
                ),
            ),
            footer,
            class_name=(
                "divide-y divide-gray-200 dark:divide-white/10 "
                "rounded-xl overflow-hidden "
                "outline outline-1 outline-gray-200 dark:outline-white/10 "
                f"shadow-md {class_name}"
            ),
        )


class CardNamespace(SimpleNamespace):
    """A namespace for card-related components."""

    __call__ = staticmethod(CardRoot)
    Header = staticmethod(CardHeader)
    Footer = staticmethod(CardFooter)


Card = CardNamespace()
