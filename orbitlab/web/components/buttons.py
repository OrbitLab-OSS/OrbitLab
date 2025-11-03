from types import SimpleNamespace

import reflex as rx


class PrimaryButton:
    def __new__(cls, text: str, *, icon: str | None = None, **props: dict):
        return rx.el.button(
            rx.icon(icon, size=16, class_name="mr-2") if icon else rx.fragment(),
            text,
            class_name=(
                "inline-flex items-center rounded-md px-3 py-2 text-sm font-semibold "
                "text-white bg-gradient-to-r from-[#1E63E9] to-[#36E2F4] "
                "hover:opacity-90 active:opacity-80 "
                "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:opacity-40 "
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#36E2F4]/40 "
                "transition-all duration-200 shadow-md shadow-[#36E2F4]/30"
            ),
            form=props.pop("form", None),
            on_click=props.pop("on_click", None),
            disabled=props.pop("disabled", False),
        )


class SecondaryButton:
    def __new__(cls, text: str, *, icon: str | None = None, **props: dict):
        return rx.el.button(
            rx.icon(icon, size=16, class_name="mr-2") if icon else rx.fragment(),
            text,
            class_name=(
                "inline-flex items-center rounded-md px-3 py-2 text-sm font-semibold "
                "text-gray-900 dark:text-[#E8F1FF] "
                "bg-gradient-to-b from-white/10 to-white/[0.05] "
                "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:opacity-40 "
                "hover:bg-white/20 active:bg-white/30 "
                "backdrop-blur-sm shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)] "
                "transition-all duration-200"
            ),
            form=props.pop("form", None),
            on_click=props.pop("on_click", None),
            disabled=props.pop("disabled", False),
        )


class IconButton:
    def __new__(cls, icon: str, **props: dict):
        return rx.el.button(
            rx.icon(icon, size=props.pop("size", 16)),
            class_name=(
                "p-3 rounded-full text-[rgb(0,150,255)] transition-all duration-200 ease-in-out "
                "hover:border hover:scale-105 hover:text-[rgb(0,200,255)] hover:bg-[rgba(0,150,255,0.1)] "
                "hover:border-[rgba(0,200,255,0.5)] hover:shadow-[0_0_6px_rgba(0,150,255,0.25)] cursor-pointer"
            ),
        )


class ButtonsNamespace(SimpleNamespace):
    Primary = staticmethod(PrimaryButton)
    Secondary = staticmethod(SecondaryButton)
    Icon = staticmethod(IconButton)


Buttons = ButtonsNamespace()
