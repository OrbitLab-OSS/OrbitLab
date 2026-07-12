import asyncio
from typing import Literal

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.redis.clients import LogsClient
from orbitlab.web import tailwind
from orbitlab.web.layout import orbitlab_page


class LogsState(rx.State):
    current: rx.Field[Literal["system", "workflows"]] = rx.field(default="workflows")
    workflow_logs: rx.Field[list[str]] = rx.field(default_factory=list)
    workflow_logs_last_id: rx.Field[str] = rx.field(default="")
    system_logs: rx.Field[list[str]] = rx.field(default_factory=list)
    system_logs_last_id: rx.Field[str] = rx.field(default="")
    countdown_refresh_seconds: rx.Field[int] = rx.field(default=5)
    auto_refresh: rx.Field[bool] = rx.field(default=False)

    @rx.var(cache=False)
    def workflow_logs_string(self) -> str:
        return "\n".join(reversed(self.workflow_logs))

    @rx.var(cache=False)
    def system_logs_string(self) -> str:
        return "\n".join(reversed(self.system_logs))

    @rx.event
    async def set_log_view(self, log_type: Literal["system", "workflows"]) -> FrontendEvents:
        self.current = log_type
        return LogsState.scroll_logs

    @rx.event
    async def scroll_logs(self) -> FrontendEvents:
        return rx.call_script(
            f"document.getElementById('{self.current}-log-output').scrollIntoView({{ behavior: 'smooth', block: 'end' }});"
        )

    @rx.event(background=True)
    async def stream_logs(self) -> FrontendEvents:
        async with self:
            self.auto_refresh = True
        while self.countdown_refresh_seconds != 0:
            async with self:
                self.countdown_refresh_seconds -= 1
            await asyncio.sleep(1)
            if not self.auto_refresh:
                break
        if self.auto_refresh:
            async with self:
                self.countdown_refresh_seconds = 5
            return [
                LogsState.manual_refresh,
                LogsState.stream_logs
            ]
        
    @rx.event
    async def cancel_auto_refresh(self) -> FrontendEvents:
        self.auto_refresh = False
        self.countdown_refresh_seconds = 5

    @rx.event
    async def manual_refresh(self) -> None:
        client = LogsClient()
        if self.current == "workflows":
            last_id, workflow_logs = await client.get_workflow_logs()
            # if there's no new logs, it returns and empty string and empty list
            if last_id:
                self.workflow_logs_last_id = last_id
            self.workflow_logs = workflow_logs + self.workflow_logs
        else:
            last_id, system_logs = await client.get_system_logs()
            # if there's no new logs, it returns and empty string and empty list
            if last_id:
                self.system_logs_last_id = last_id
            self.system_logs = system_logs + self.system_logs
        return LogsState.scroll_logs

    @rx.event
    async def on_load(self) -> FrontendEvents:
        self.auto_refresh = False
        self.countdown_refresh_seconds = 5
        
        client = LogsClient()
        self.system_logs_last_id, self.system_logs = await client.get_system_logs()
        self.workflow_logs_last_id, self.workflow_logs = await client.get_workflow_logs()
        self.current = "workflows"


@rx.page("/logs", on_load=LogsState.on_load)
@orbitlab_page
def logs_dashboard() -> rx.Component:
    return rx.el.div(
        tailwind.PageHeader(
            "Audit Logs",
            rx.cond(
                LogsState.auto_refresh,
                tailwind.Buttons.Secondary(
                    rx.el.div(
                        "Cancel",
                        rx.progress(value=LogsState.countdown_refresh_seconds, max=5),
                    ),
                    on_click=LogsState.cancel_auto_refresh,
                ),
                tailwind.Buttons.Secondary(
                    "Refresh",
                    on_click=LogsState.manual_refresh,
                ),
            ),
            tailwind.Buttons.Secondary(
                "System",
                on_click=LogsState.set_log_view("system"),
                disabled=LogsState.current == "system"
            ),
            tailwind.Buttons.Secondary(
                "Workflows",
                on_click=LogsState.set_log_view("workflows"),
                disabled=LogsState.current == "workflows"
            ),
        ),
        rx.el.div(
            rx.cond(
                LogsState.current == "system",
                rx.code_block(
                    language="log",
                    code=LogsState.system_logs_string,
                    code_tag_props={"style": {"whiteSpace": "pre-wrap"}},
                    show_line_numbers=False,
                    id=rx.vars.StringVar.create("system-log-output"),
                ),
                rx.code_block(
                    language="log",
                    code=LogsState.workflow_logs_string,
                    code_tag_props={"style": {"whiteSpace": "pre-wrap"}},
                    show_line_numbers=False,
                    id=rx.vars.StringVar.create("workflows-log-output"),
                ),
            ),
            class_name="mt-5 w-full h-full overflow-auto",
            on_mount=LogsState.scroll_logs
        ),
        rx.el.div(
            rx.text("Resume", class_name="text-sm font-medium text-gray-800 dark:text-gray-100"),
            class_name=(
                "w-full h-fit flex justify-center items-center py-1 rounded-lg cursor-pointer select-none "
                "bg-gradient-to-b from-white/80 to-gray-100/60 dark:from-[#0E1015]/80 dark:to-[#12141A]/80 "
                "backdrop-blur-sm border border-gray-200/70 dark:border-white/[0.08] shadow-sm hover:shadow-md "
                "hover:ring-1 hover:ring-[#36E2F4]/30 hover:dark:ring-[#36E2F4]/40 active:scale-[0.98] "
                "active:shadow-inner transition-all duration-200 ease-in-out data-[active=true]:hidden"
            ),
            on_click=LogsState.stream_logs,
            data_active=LogsState.auto_refresh,
        ),
        class_name="w-full min-h-fit max-h-5/6 h-fit"
    )
