import reflex as rx


class RadioItem:
    def __new__(cls, item: str, label: str | None = None, **props: dict) -> rx.Component:
        class_name = props.pop("class_name", "")
        value = props.pop("value", None)
        return rx.el.label(
            # Hidden native radio (peer) + styled button-like label
            rx.el.input(
                type="radio",
                id=item,
                class_name="peer sr-only",
                checked=rx.cond(value == item, True, False),  # noqa: FBT003
                **props,
            ),
            rx.el.span(
                rx.el.span(label or item.title(), class_name="truncate"),
                class_name=(
                    # Layout & typography
                    "inline-flex items-center justify-center px-4 py-2 rounded-lg text-sm font-medium "
                    "transition-all duration-200 select-none "
                    # Theme base
                    "text-gray-800 dark:text-gray-200 "
                    "bg-gradient-to-b from-gray-50/95 to-gray-200/70 "
                    "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                    "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)] "
                    "border border-gray-200 dark:border-white/[0.08] "
                    # Hover/focus
                    "hover:ring-1 hover:ring-[#36E2F4]/35 "
                    "focus:outline-none focus-visible:ring-2 focus-visible:ring-[#36E2F4]/40 "
                    # Checked state via peer
                    "peer-checked:text-[#1E63E9] dark:peer-checked:text-[#36E2F4] "
                    "peer-checked:bg-[#1E63E9]/10 dark:peer-checked:bg-[#36E2F4]/10 "
                    "peer-checked:border-[#1E63E9]/40 dark:peer-checked:border-[#36E2F4]/40 "
                    "peer-checked:shadow-[0_0_10px_rgba(54,226,244,0.15)] "
                    # Disabled
                    "peer-disabled:opacity-40 peer-disabled:cursor-not-allowed " + class_name
                ),
                # For screen readers / better click target
                aria_hidden="true",
            ),
            html_for=item,
            class_name="cursor-pointer",
        )


class RadioGroup:
    Item = staticmethod(RadioItem)

    def __new__(cls, *children: rx.Component, **props: dict) -> rx.Component:
        _ = props.pop("role", None)
        class_name = props.pop("class_name", "")
        return rx.el.div(
            *children,
            class_name=f"flex flex-row items-center gap-3 p-2 {class_name}",
            role="radiogroup",
            **props,
        )
