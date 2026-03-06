"""OrbitLab Web UI."""

import asyncio
from typing import Literal

import reflex as rx
import websocket
from starlette.applications import Starlette
from starlette.endpoints import WebSocketEndpoint
from starlette.exceptions import WebSocketException
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket

from orbitlab.data_types import InitializationState
from orbitlab.proxmox import Proxmox
from orbitlab.web import components
from orbitlab.web.pages import pages  # noqa: F401
from orbitlab.web.utilities import get_worker
from orbitlab.worker import Worker
from orbitlab.web.layout import orbitlab_page

from .splash_page import SplashPage, SplashPageState


class HomePageState(rx.State):
    """State management for the home page."""

    loading: bool = True


@orbitlab_page
def dashboard() -> rx.Component:
    return rx.el.div(
        class_name="w-full flex space-x-6",
    )


@rx.page("/")
def home() -> rx.Component:
    """Home page that displays either the main dashboard or splash page based on configuration status."""
    return rx.cond(
        SplashPageState.initialization_state == InitializationState.COMPLETE,
        dashboard(),
        SplashPage(),
    )


class TerminalProxy(WebSocketEndpoint):
    """WebSocket endpoint that proxies terminal connections between the browser and Proxmox."""

    encoding = "text"
    proxmox: websocket.WebSocket | None = None
    task: asyncio.Task | None = None
    event: asyncio.Event = asyncio.Event()

    async def proxmox_to_browser(self, websocket: WebSocket) -> None:
        """Forward data from the Proxmox websocket to the browser websocket."""
        if not self.proxmox:
            raise WebSocketException(code=1)

        while True:
            if self.event.is_set():
                self.proxmox.close(status=0)
                break
            data = await asyncio.to_thread(self.proxmox.recv)
            data = data.encode() if isinstance(data, str) else data
            await websocket.send_bytes(data=data)

    async def on_connect(self, websocket: WebSocket) -> None:
        """Handle a new WebSocket connection from the browser and initialize the Proxmox terminal proxy."""
        await websocket.accept()
        compute_type: Literal["qemu", "lxc"] = websocket.path_params["compute_type"]
        vmid = int(websocket.path_params["vmid"])
        self.proxmox = Proxmox().get_terminal_websocket(compute_type=compute_type, vmid=vmid)
        self.event = asyncio.Event()
        if not self.proxmox.recv() == b"OK":
            raise WebSocketException(code=1)
        self.task = asyncio.create_task(self.proxmox_to_browser(websocket=websocket))

    async def on_receive(self, _: WebSocket, data: str) -> None:
        """Handle data received from the browser and forward it to the Proxmox websocket."""
        if self.proxmox:
            self.proxmox.send(data)

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
app.register_lifespan_task(Worker().start)
