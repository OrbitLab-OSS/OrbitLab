from typing import Literal

import reflex as rx


class TabComponent:

    def __init__(self, name: str, value: str, content: rx.Component) -> None:
        self.name = name
        self.value = value
        self.content = rx.tabs.content(content, value=value, class_name="data-[orientation=horizontal]:px-5 data-[orientation=vertical]:py-5")
        self.trigger = rx.tabs.trigger(
            self.name,
            value=self.value,
            class_name=(
                "px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ease-in-out text-gray-500 "
                "dark:text-gray-400 hover:ring-1 hover:ring-[#36E2F4]/30 data-[state=active]:text-gray-900 "
                "dark:data-[state=active]:text-[#E8F1FF] data-[state=active]:bg-gradient-to-b "
                "data-[state=active]:from-gray-150/95 data-[state=active]:to-gray-300/80 "
                "dark:data-[state=active]:from-[#0E1015]/95 dark:data-[state=active]:to-[#181B22]/90 "
                "data-[state=active]:border data-[state=active]:border-gray-200 data-[state=active]:ring-1 "
                "dark:data-[state=active]:border-white/[0.08] data-[state=active]:ring-[#36E2F4]/20 "
                "data-[state=active]:shadow-[inset_0_0_0.5px_rgba(255,255,255,0.10)] "
                "dark:data-[state=active]:shadow-[inset_0_0_0.5px_rgba(255,255,255,0.08)] "
                "[&_.rt-BaseTabListTriggerInner]:!bg-transparent hover:[&_.rt-BaseTabListTriggerInner]:!bg-transparent"
            )
        )


class Tabs:

    Tab = TabComponent
    
    def __new__(cls, *tabs: TabComponent, default_value: str = "", orientation: Literal["horizontal", "vertical"] = "horizontal") -> rx.Component:
        return rx.tabs.root(
            rx.tabs.list(
                *[tab.trigger for tab in tabs],
                class_name=(
                    "inline-flex gap-2 p-1 rounded-xl border border-gray-200 dark:border-white/[0.08] "
                    "bg-gradient-to-b from-white/90 to-gray-100/70 dark:from-[#0E1015]/80 dark:to-[#181B22]/80 "
                    "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.10)] backdrop-blur-sm "
                    "dark:shadow-[inset_0_0_0.5px_rgba(255,255,255,0.08)] data-[orientation=horizontal]:w-full "
                    "data-[orientation=horizontal]:my-5 data-[orientation=vertical]:mr-5 "
                    "data-[orientation=vertical]:w-fit"
                ),
            ),
            *[tab.content for tab in tabs],
            orientation=orientation,
            default_value=default_value,
            class_name="w-full h-full flex data-[orientation=horizontal]:flex-col"
        )
