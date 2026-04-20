"""OrbitLab Callout Component."""

import uuid
from typing import Literal, TypedDict, Unpack

import reflex as rx


class Props(TypedDict, total=False):
    """Type definition for Callout component props."""

    type: Literal["info", "success", "warning", "error"]
    dismiss: bool
    class_name: str


class Callout:
    """OrbitLab-styled callout component."""

    def __new__(cls, text: str, **props: Unpack[Props]) -> rx.Component:
        """Create and return the component."""
        data_type = props.pop("type", "info")
        class_name = props.pop("class_name", "")
        can_dismiss = props.pop("dismiss", False)
        input_id = str(uuid.uuid4())
        return rx.el.div(
            rx.el.input(
                id=input_id,
                type="checkbox",
                class_name="hidden",
            ),
            rx.callout(
                rx.fragment(
                    rx.text(text, class_name="mr-4"),
                    rx.el.button(
                        rx.icon("x", class_name="w-4 h-4"),
                        data_dismiss=can_dismiss,
                        class_name=(
                            "absolute top-2 right-2 opacity-60 rounded-md hover:opacity-100 hover:border "
                            "transition-opacity duration-200 hidden data-[dismiss=true]:inline-block"
                        ),
                        on_click=rx.set_value(ref=input_id, value=True),
                    ),
                ),
                icon={
                    "info": "info",
                    "success": "circle-check-big",
                    "warning": "circle-alert",
                    "error": "circle-x",
                }.get(data_type),
                data_type=data_type,
                class_name=(
                    "rounded-xl p-4 flex gap-2 m-2 font-bold bg-gradient-to-b from-gray-100/90 to-gray-200/70 "
                    "dark:from-[#0E1015]/80 dark:to-[#12141A]/80 backdrop-blur-sm transition-all duration-300 "
                    "data-[type=info]:border-[#1E63E9] data-[type=info]:dark:border-[#36E2F4] "
                    "data-[type=info]:dark:**:text-[#36E2F4] data-[type=info]:**:text-[#1E63E9] "
                    "data-[type=info]:shadow-[0_0_20px_0_rgba(30,99,233,0.5)] "
                    "data-[type=info]:dark:shadow-[0_0_20px_0_rgba(54,226,244,0.5)] "
                    "data-[type=success]:border-emerald-600/30 data-[type=success]:dark:border-emerald-400/30 "
                    "data-[type=success]:**:text-emerald-600 data-[type=success]:dark:**:text-emerald-400 "
                    "data-[type=success]:shadow-[0_0_20px_0_rgba(52,211,153,0.5)] "
                    "data-[type=warning]:border-amber-500 data-[type=warning]:shadow-[0_0_20px_0_rgba(251,191,36,0.5)] "
                    "data-[type=warning]:**:text-amber-500 "
                    "data-[type=error]:border-red-400 data-[type=error]:shadow-[0_0_20px_0_rgba(248,113,113,0.5)] "
                    f"data-[type=error]:**:text-red-400 {class_name}"
                ),
            ),
            class_name="w-full flex [&:has(input[value]:not([value='']))]:hidden",
        )
