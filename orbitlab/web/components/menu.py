import reflex as rx


class MenuItem:
    def __new__(cls, text: str, on_click: rx.EventHandler[rx.event.no_args_event_spec], **props: dict) -> rx.Component:
        class_name = props.pop("class_name", "")
        return rx.dropdown_menu.item(
            text,
            on_click=on_click,
            class_name=(
                "p-3 rounded-full text-[rgb(0,150,255)] transition-all duration-200 ease-in-out "
                "hover:border hover:scale-105 hover:text-[rgb(0,200,255)] hover:bg-[rgba(0,150,255,0.1)] "
                "hover:border-[rgba(0,200,255,0.5)] hover:shadow-[0_0_6px_rgba(0,150,255,0.25)] cursor-pointer "
                f"{class_name}"
            ),
            **props,
        )


class Menu:
    Item = staticmethod(MenuItem)
    Separator = staticmethod(rx.dropdown_menu.separator)

    def __new__(cls, trigger: rx.Component, *children: rx.Component, **props: dict) -> rx.Component:
        return rx.dropdown_menu.root(
            rx.dropdown_menu.trigger(trigger),
            rx.dropdown_menu.content(*children),
            **props,
        )
