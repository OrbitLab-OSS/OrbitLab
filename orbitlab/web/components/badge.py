"""Badge component for OrbitLab, styled for light/dark themes."""

from typing import ClassVar, Literal, TypeAlias

import reflex as rx

Colors: TypeAlias = Literal["default", "blue", "green", "red", "orange"]
StatusContent: TypeAlias = str | rx.Component | rx.Var


class WithStatus:
    color_classes: ClassVar[dict[Colors, str]] = {
        "default": (
            "bg-gradient-to-b from-gray-100 to-gray-200 "
            "text-gray-700 border border-gray-300 "
            "dark:from-[#0E1015] dark:to-[#181B22] "
            "dark:text-gray-300 dark:border-white"
        ),
        "blue": (
            "bg-gradient-to-b from-[#E0F2FE] to-[#BFDBFE] "
            "text-[#1E63E9] border border-[#93C5FD] "
            "dark:from-[#1E63E9] dark:to-[#36E2F4] "
            "dark:text-black dark:border-[#36E2F4]"
        ),
        "green": (
            "bg-gradient-to-b from-[#DCFCE7]/80 to-[#BBF7D0]/70 "
            "text-[#16A34A] border border-[#86EFAC]/60 "
            "dark:from-[#16A34A]/20 dark:to-[#4ADE80]/10 "
            "dark:text-[#4ADE80] dark:border-[#4ADE80]/30"
        ),
        "red": (
            "bg-gradient-to-b from-[#FEE2E2] to-[#FCA5A5] "
            "text-black border border-[#FCA5A5] "
            "dark:from-[#DC2626] dark:to-[#F87171] "
            "dark:text-white dark:border-[#F87171]"
        ),
        "orange": (
            "bg-gradient-to-b from-[#FFEDD5]/80 to-[#FED7AA]/70 "
            "text-[#EA580C] border border-[#FDBA74]/60 "
            "dark:from-[#EA580C]/20 dark:to-[#FB923C]/10 "
            "dark:text-[#FB923C] dark:border-[#FB923C]/30"
        ),
    }

    def __new__(
        cls,
        component: rx.Component,
        *,
        status_content: StatusContent | None = None,
        color: Colors = "default",
    ):
        if status_content is None:
            status_content = rx.fragment()
        return rx.el.div(
            component,
            rx.el.span(
                status_content,
                class_name=(
                    "absolute -top-1 -right-1 block rounded-full px-1 "
                    f"{cls.color_classes.get(color, cls.color_classes['default'])}"
                ),
            ),
            class_name="relative flex items-center justify-center mr-4",
        )


class Badge:
    """OrbitLab-themed badge component."""

    color_classes: ClassVar[dict[Colors, str]] = {
        "default": (
            "bg-gradient-to-b from-gray-100/90 to-gray-200/60 "
            "text-gray-700 border border-gray-300/60 "
            "dark:from-[#0E1015]/90 dark:to-[#181B22]/80 "
            "dark:text-gray-300 dark:border-white/[0.06]"
        ),
        "blue": (
            "bg-gradient-to-b from-[#E0F2FE]/80 to-[#BFDBFE]/70 "
            "text-[#1E63E9] border border-[#93C5FD]/60 "
            "dark:from-[#1E63E9]/20 dark:to-[#36E2F4]/10 "
            "dark:text-[#36E2F4] dark:border-[#36E2F4]/30"
        ),
        "green": (
            "bg-gradient-to-b from-[#DCFCE7]/80 to-[#BBF7D0]/70 "
            "text-[#16A34A] border border-[#86EFAC]/60 "
            "dark:from-[#16A34A]/20 dark:to-[#4ADE80]/10 "
            "dark:text-[#4ADE80] dark:border-[#4ADE80]/30"
        ),
        "red": (
            "bg-gradient-to-b from-[#FEE2E2]/80 to-[#FCA5A5]/70 "
            "text-[#DC2626] border border-[#FCA5A5]/50 "
            "dark:from-[#DC2626]/20 dark:to-[#F87171]/10 "
            "dark:text-[#F87171] dark:border-[#F87171]/30"
        ),
        "orange": (
            "bg-gradient-to-b from-[#FFEDD5]/80 to-[#FED7AA]/70 "
            "text-[#EA580C] border border-[#FDBA74]/60 "
            "dark:from-[#EA580C]/20 dark:to-[#FB923C]/10 "
            "dark:text-[#FB923C] dark:border-[#FB923C]/30"
        ),
    }

    def __new__(
        cls,
        label: str,
        color_scheme: Colors = "default",
        size: Literal["sm", "md", "lg"] = "md",
        icon: str | None = None,
        **props: dict,
    ) -> rx.Component:
        """Create an OrbitLab badge.

        Args:
            label: The text to display inside the badge.
            color_scheme: The color style, e.g. "default", "blue", "green", "red", "orange".
            size: One of "sm", "md", or "lg".
            icon: Optional lucide-react icon name.
        """
        size_classes = {
            "sm": "text-xs px-2 py-0.5 rounded-md",
            "md": "text-sm px-2.5 py-0.5 rounded-lg",
            "lg": "text-base px-3 py-1 rounded-lg",
        }

        icon_component = rx.icon(icon, size=14, class_name="mr-1.5") if icon else rx.fragment()

        return rx.el.span(
            rx.el.div(
                icon_component,
                rx.el.span(label),
                class_name=(
                    "inline-flex items-center font-medium tracking-wide "
                    f"{size_classes[size]} {cls.color_classes.get(color_scheme, cls.color_classes['default'])} "
                    "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.25)] "
                    "backdrop-blur-sm transition-all duration-200 ease-in-out"
                ),
            ),
            **props,
        )
