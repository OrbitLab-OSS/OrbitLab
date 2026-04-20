"""OrbitLab Web UI."""

import asyncio
import random
from typing import Literal

import reflex as rx
from starlette.applications import Starlette
from starlette.endpoints import WebSocketEndpoint
from starlette.exceptions import WebSocketException
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket
from websockets.asyncio import client as websocket

# from orbitlab.constants import Directories
# from orbitlab.data_types import InitializationStatus
from orbitlab.proxmox import Proxmox
from orbitlab.web import tailwind
# from orbitlab.web.tailwind.initializer import ConfigureBackplaneDialog, ConfigureDefaultsDialog, ErrorDialog, InitializationState
from orbitlab.web.pages import pages  # noqa: F401
from orbitlab.worker import Worker
from orbitlab.web.layout import orbitlab_page


@orbitlab_page
def dashboard() -> rx.Component:
    return rx.el.div(
        class_name="w-full flex space-x-6",
    )


class FooState(rx.State):
    bar: bool = True

    
@rx.page("/")
def home() -> rx.Component:
    """Home page that displays either the main dashboard or splash page based on configuration status."""
    return rx.cond(
        # InitializationState.status == InitializationStatus.COMPLETE,
        FooState.bar,
        dashboard(),
        rx.box(
            rx.box(
                rx.el.svg(
                    *[
                        rx.el.circle(
                            cx=f"{x}%",
                            cy=f"{y}%",
                            r=f"{r:.1f}",
                            fill="#E8F1FF",
                            opacity="0",
                            style={"--dx": str(y), "--dy": str(x), "--duration": f"{duration}s"},
                            class_name="star",
                        )
                        for x, y, r, duration in [
                            (
                                random.randint(1, 99),  # noqa: S311
                                random.randint(1, 99),  # noqa: S311
                                random.uniform(0.1, 2.1),  # noqa: S311
                                random.randint(5, 15),  # noqa: S311
                            )
                            for _ in range(random.randint(15, 20))  # noqa: S311
                        ]
                    ],
                    xmlns="http://www.w3.org/2000/svg",
                    viewBox="0 0 200 200",
                    fill="none",
                    class_name="w-full h-full",
                ),
                class_name="absolute inset-0",
            ),
            tailwind.OrbitLabLogo(size=150, animated=True),
            # rx.box(
            #     rx.text(
            #         "OrbitLab",
            #         class_name="text-[#E8F1FF] font-semibold tracking-widest text-2xl mt-8 fade-title",
            #     ),
            #     rx.cond(
            #         InitializationState.status == InitializationStatus.NOT_STARTED,
            #         rx.el.div(
            #             tailwind.Buttons.Primary("Initialize", on_click=InitializationState.phase_1),
            #             class_name=(
            #                 "w-full flex items-center justify-center mt-6 animate-[fadeInUp_3s_ease-in-out] "
            #                 "relative z-10"
            #             ),
            #         ),
            #         rx.text(
            #             InitializationState.process_info,
            #             class_name="text-[#36E2F4] text-sm mt-2 fade-subtitle",
            #         ),    
            #     ),
            #     class_name="flex flex-col items-center justify-center",
            # ),
            # ErrorDialog(),
            # ConfigureBackplaneDialog(),
            # ConfigureDefaultsDialog(),
            class_name=(
                "relative flex flex-col items-center justify-center min-h-screen w-full "
                "bg-[#0E1015] overflow-hidden select-none"
            ),
        ),
    )


class TerminalProxy(WebSocketEndpoint):
    """WebSocket endpoint that proxies terminal connections between the browser and Proxmox."""

    encoding = "text"
    proxmox: websocket.ClientConnection | None = None
    task: asyncio.Task | None = None
    event: asyncio.Event = asyncio.Event()

    async def proxmox_to_browser(self, websocket: WebSocket) -> None:
        """Forward data from the Proxmox websocket to the browser websocket."""
        if not self.proxmox:
            raise WebSocketException(code=1)

        while True:
            if self.event.is_set():
                await self.proxmox.close()
                break
            data = await self.proxmox.recv()
            await websocket.send_bytes(data=data)

    async def on_connect(self, websocket: WebSocket) -> None:
        """Handle a new WebSocket connection from the browser and initialize the Proxmox terminal proxy."""
        await websocket.accept()
        compute_type: Literal["qemu", "lxc"] = websocket.path_params["compute_type"]
        vmid = int(websocket.path_params["vmid"])
        self.proxmox = await Proxmox().get_terminal_websocket(compute_type=compute_type, vmid=vmid)
        self.event = asyncio.Event()
        if not await self.proxmox.recv(decode=True) == "OK":
            raise WebSocketException(code=1)
        self.task = asyncio.create_task(self.proxmox_to_browser(websocket=websocket))

    async def on_receive(self, _: WebSocket, data: str) -> None:
        """Handle data received from the browser and forward it to the Proxmox websocket."""
        if self.proxmox:
            await self.proxmox.send(data)

    async def on_disconnect(self, websocket: WebSocket, _: int) -> None:
        """Handle the disconnection of the WebSocket and clean up resources."""
        self.event.set()
        if self.task:
            await asyncio.gather(self.task)
        await websocket.close()


app = rx.App(
    stylesheets=["animations.css"],
    api_transformer=Starlette(
        routes=[
            WebSocketRoute("/ws/terminal/{compute_type}/{vmid}", endpoint=TerminalProxy),
        ],
    ),
)
# Directories().make_dirs()
app.register_lifespan_task(Worker().start)
