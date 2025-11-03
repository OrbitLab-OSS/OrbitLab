from typing import TypedDict, Unpack

import reflex as rx


class Props(TypedDict, total=False):
    on_change: rx.EventHandler[rx.event.input_event]
    description: str
    placeholder: str
    value: str
    type: str
    error: str
    icon: str
    class_name: str
    wrapper_class_name: str


class Input:
    def __new__(cls, **props: Unpack[Props]) -> rx.Component:
        props.setdefault("type", "text")
        props.setdefault("error", "Invalid input")
        icon = props.pop("icon", None)
        error = props.pop("error", None)
        description = props.pop("description", None)
        wrapper_class_name = props.pop("wrapper_class_name", "w-full")

        icon_component = (
            rx.el.div(
                rx.icon(icon, size=16, class_name="text-gray-400 dark:text-gray-500"),
                class_name="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3",
            ) if icon else rx.fragment()
        )

        return rx.el.div(
            rx.el.div(
                icon_component,
                rx.input(
                    class_name=(
                        "w-full rounded-lg px-3 py-1 outline-none text-base data-[icon=true]:pl-9 "
                        "font-medium transition-all duration-300 ease-in-out "
                        "bg-gradient-to-b from-gray-50/95 to-gray-200/80 "
                        "border border-gray-200 text-gray-800 "
                        "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                        "dark:text-gray-100 dark:border-white/[0.08] "
                        "group-has-user-invalid:border-rose-400 group-has-user-invalid:focus:ring-rose-400/40 "
                        "placeholder-gray-400 dark:placeholder-gray-500 "
                        "hover:ring-1 hover:ring-[#36E2F4]/30 "
                        "focus:ring-2 focus:ring-[#36E2F4]/40 "
                        "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.10)] "                        
                    ),
                    data_icon=bool(icon),
                    **props,
                ),
                data_icon=bool(icon),
                class_name="data[icon=true]:relative",
            ),
            rx.el.p(error, class_name="hidden mt-1 text-sm text-rose-400 group-has-user-invalid:block"),
            rx.cond(
                description,
                rx.el.p(
                    description,
                    class_name="mt-1 text-sm text-gray-500 dark:text-gray-400 group-has-user-invalid:hidden",
                ),
            ),
            class_name=f"group flex flex-col {wrapper_class_name}",
        )
