from collections.abc import Sequence

import reflex as rx


class Select:
    @classmethod
    def __option__(cls, option: str | Sequence[str]) -> rx.Component:
        class_name = (
            "bg-gradient-to-b from-gray-50/95 to-gray-200/80 text-gray-800 dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
            "dark:text-gray-100"
        )
        match (option):
            case rx.vars.ArrayVar():
                return rx.select.item(option[0], value=option[1], class_name=class_name)
            case rx.vars.StringVar():
                return rx.select.item(option, value=option, class_name=class_name)

    def __new__(cls, options: Sequence[str] | dict[str, str], **props: dict) -> rx.Component:
        error=props.pop("error", "Invalid selection")
        wrapper_class = props.pop('class_name', '')
        class_name=(
            # Base size and shape
            "px-3 py-2 outline-none rounded-lg "
            "text-sm font-medium transition-all duration-300 ease-in-out "
            # Light mode background & border
            "bg-gradient-to-b from-gray-50/95 to-gray-200/80 "
            "border border-gray-200 text-gray-800 "
            # Dark mode background & border
            "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
            "dark:text-gray-100 dark:border-white/[0.08] "
            # Hover/focus styles
            "hover:ring-1 hover:ring-[#36E2F4]/30 "
            "focus:ring-2 focus:ring-[#36E2F4]/40 focus:border-[#36E2F4]/40 "
            # Subtle inner shadow (chrome feel)
            "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)]"
        )
        return rx.el.div(
            rx.select.root(
                rx.select.trigger(placeholder=props.pop("placeholder", "Select Item"), class_name=class_name),
                rx.select.content(rx.foreach(options, lambda opt: cls.__option__(opt))),
                align=props.pop("align", "center"),
                class_name=class_name,
                **props,
            ),
            rx.el.p(error, class_name="hidden mt-1 text-sm text-rose-400 group-has-user-invalid:block"),
            class_name=f"group {wrapper_class}"
        )
