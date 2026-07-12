from abc import ABC, abstractmethod

import reflex as rx
from reflex_components_radix.themes.components.dropdown_menu import DropdownMenuRoot

from .buttons import Buttons


class Table(ABC):

    @staticmethod
    def column_header(header: str | rx.Var[str], index: int) -> rx.el.Th:
        return rx.el.th(
            header,
            id=f"header-{index}",
            class_name=(
                "px-6 py-3 text-left text-xs font-semibold tracking-wider uppercase text-gray-600 dark:text-[#AEB9CC]"
            )
        )

    @abstractmethod
    def row(cls, row: rx.vars.ObjectVar) -> list[rx.Component]: ...
    
    @classmethod
    def _row(cls, row: rx.vars.ObjectVar, index: int) -> rx.Component:
        return rx.el.tr(
            *[
                rx.el.td(
                    cell,
                    data_is_menu=rx.Var.create(isinstance(cell, DropdownMenuRoot)),
                    class_name=(
                        "px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300 "
                        "data-[is-menu=true]:justify-end"
                    ),
                ) for cell in cls.row(row)
            ],
            id=f"row-{index}",
            class_name=(
                "transition-colors duration-200 "
                "hover:bg-gray-100/60 dark:hover:bg-white/[0.06] "
                "hover:text-gray-900 dark:hover:text-[#E8F1FF]"
            ),
        )

    def __new__(cls, name: str, headers: list[str] | rx.vars.ArrayVar[str], data: rx.vars.ArrayVar, refresh: rx.event.EventCallback, class_name: str = "") -> rx.Component:
        if isinstance(headers, list):
            headers = rx.Var.create(headers)
        return rx.el.div(
            rx.el.div(
                rx.text(name),
                Buttons.Icon("refresh-ccw",  on_click=refresh),
                class_name=(
                    "w-full p-2 rounded-t-lg bg-white/60 dark:bg-white/[0.03] text-gray-600 dark:text-[#AEB9CC] "
                    "backdrop-blur-sm flex justify-between"
                )
            ),
            # Table Container
            rx.el.div(
                rx.el.table(
                    rx.el.thead(
                        rx.el.tr(rx.foreach(headers, cls.column_header)),
                        class_name="sticky top-0 z-20 bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.cond(
                            data.length() > 0,
                            rx.foreach(data, lambda row, index: cls._row(row, index)),  # noqa: PLW0108
                            rx.el.tr(
                                rx.el.td(
                                    "No Data to Display",
                                    col_span=headers.length(),
                                    align="center",
                                    class_name="py-10"
                                ),
                            ),
                        ),
                        class_name=(
                            "divide-y divide-gray-200 dark:divide-white/[0.08] bg-white/70 dark:bg-[#0E1015]/60 "
                            "backdrop-blur-sm"
                        ),
                    ),
                    class_name="w-full border-collapse table-auto min-w-full text-sm text-gray-800 dark:text-gray-200",
                ),
                class_name=(
                    "w-full h-5/6 min-h-0 flex-1 overflow-auto "
                    "shadow-md bg-gradient-to-b from-white/90 to-gray-50/70 dark:from-[#0E1015]/80 "
                    "dark:to-[#12141A]/80 "
                ),
            ),
            # Footer
            rx.el.div(class_name="w-full h-[25px] rounded-b-lg bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm"),
            class_name=(
                "w-full max-h-5/6 min-h-0 flex-col overflow-hidden rounded-lg mt-5 border border-gray-200 "
                "dark:border-white/[0.08] hover:ring-1 hover:ring-[#36E2F4]/40 transition-all duration-200 "
                f"{class_name}"
            )
        )
