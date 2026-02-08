"""OrbitLab Web UI."""

from abc import ABC
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from enum import auto
from re import M
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
import reflex as rx
import websocket
from starlette.applications import Starlette
from starlette.endpoints import WebSocketEndpoint
from starlette.exceptions import WebSocketException
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket

from orbitlab.clients.proxmox import Proxmox
from orbitlab.data_types import InitializationState, StrEnum
from orbitlab.web import components
from orbitlab.web.pages import pages  # noqa: F401

from .splash_page import SplashPage, SplashPageState


class HomePageState(rx.State):
    """State management for the home page."""

    loading: bool = True


from redis.asyncio import Redis
from redis import exceptions


class EventStatus(StrEnum):
    IN_PROGRESS = "in-progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WorkflowState(StrEnum):
    PENDING = auto()
    VALIDATING = auto()
    PROVISIONING = auto()
    CONFIGURING = auto()
    FINALIZING = auto()
    COMPLETE = auto()
    FAILED = auto()


class OrbitLabEvent(BaseModel):
    name: str
    schema: str
    job_id: str
    status: EventStatus


class WorkflowPayload(BaseModel):
    state: WorkflowState


class Workflow(ABC):
    TYPE: str
    SCHEMA: str
    PAYLOAD: type[WorkflowPayload]

    def __init__(self, redis: Redis, event: OrbitLabEvent) -> None:
        """Initialize the workflow."""
        self.redis = redis
        self.event = event

    async def get_payload(self) -> None:
        print("GET", f"ol:workflow:{self.TYPE}:{self.SCHEMA}:{self.event.job_id}")
        resposne = await self.redis.get(name=f"ol:workflow:{self.TYPE}:{self.SCHEMA}:{self.event.job_id}")
        print(resposne)

    # async def run_once(self) -> None:
    #     payload = await self.get_payload()
    #     match payload.state:
    #         case WorkflowState.PENDING:
    #             await self.transition_to(WorkflowState.VALIDATING)

    #         case WorkflowState.VALIDATING:
    #             await self.validate()
    #             await self.transition_to(WorkflowState.PROVISIONING)

    #         case WorkflowState.PROVISIONING:
    #             await self.create_lxc()
    #             await self.transition_to(WorkflowState.CONFIGURING)

    #         case WorkflowState.CONFIGURING:
    #             await self.configure()
    #             await self.transition_to(WorkflowState.WAITING_FOR_IP)

    #         case WorkflowState.WAITING_FOR_IP:
    #             if await self.has_ip():
    #                 await self.transition_to(WorkflowState.FINALIZING)

    #         case WorkflowState.FINALIZING:
    #             await self.finalize()
    #             await self.transition_to(WorkflowState.DONE)

    #         case WorkflowState.DONE | WorkflowState.FAILED:
    #             return


class ComputeCreate(WorkflowPayload):
    compute_type: Literal["lxc", "qemu"]
    manifest: str
    state: WorkflowState


class LXCCreateV1(Workflow):
    TYPE = "lxc.create"
    SCHEMA = "v1"
    PAYLOAD: type[ComputeCreate] = ComputeCreate


class WorkflowRegistry:
    """OrbitLab Workflow Registry used by the Worker to execute workflows from events."""

    def __init__(self) -> None:
        """Initialize workflow registry."""
        self._registry: dict[tuple[str, str], type[Workflow]] = {}

    def register(self, workflow_cls: type[Workflow]) -> None:
        """Register workflow class based on event type and schema version."""
        key = (workflow_cls.TYPE, workflow_cls.SCHEMA)
        if key in self._registry:
            _type, schema = key
            msg = f"Duplicate workflow registered: {_type}@{schema}"
            raise RuntimeError(msg)
        self._registry[key] = workflow_cls

    def resolve(self, *, event: OrbitLabEvent) -> type[Workflow]:
        """Resolve event to workflow class."""
        try:
            return self._registry[(event.name, event.schema)]
        except KeyError as err:
            msg = f"No workflow registered for {event.name}@{event.schema}"
            raise RuntimeError(msg) from err


type StreamEventData = tuple[bytes, dict[bytes, bytes]]
type RedisStreamEvent = tuple[bytes, tuple[StreamEventData]]

class Worker:
    """OrbitLab Event Worker."""

    def __init__(self) -> None:
        """Initialize the worker."""
        self.redis = Redis(host="192.168.87.230", port=6379)
        self.task: asyncio.Task | None = None
        self.event = asyncio.Event()
        self.registry = WorkflowRegistry()
        self._workflows = set()
        self._register_workflows_()

    def _register_workflows_(self) -> None:
        self.registry.register(LXCCreateV1)

    async def _parse_event_(self, stream_event: RedisStreamEvent) -> OrbitLabEvent:
        stream, event_data = stream_event
        _event_data = event_data[0]
        event_id, payload = _event_data
        print(f"Parsing stream {stream} event {event_id}")
        return OrbitLabEvent.model_validate({key.decode(): value.decode() for key, value in payload.items()})

    async def _run_(self) -> None:
        while True:
            stream_events = await self.redis.xreadgroup(
                groupname="ol:workers",
                consumername="pve-1-2",
                streams={"ol:events": ">"},
                count=1,
            )
            if stream_events:
                event = await self._parse_event_(stream_event=stream_events[0])
                workflow_cls = self.registry.resolve(event=event)
                print(workflow_cls)
                workflow = asyncio.create_task(workflow_cls(redis=self.redis, event=event).get_payload())
                # workflow = asyncio.create_task(workflow_cls(redis=self.redis, event=event).run_once())
                self._workflows.add(workflow)
                workflow.add_done_callback(self._workflows.discard)
            if self.event.is_set():
                print("Exiting...")
                break
            await asyncio.sleep(1)

    @classmethod
    async def create_workflow(cls, workflow: type[Workflow], payload: WorkflowPayload) -> None:
        redis = Redis(host="192.168.87.230", port=6379)
        name = f"ol:workflow:{workflow.TYPE}:{workflow.SCHEMA}:test-uuid"
        response = await redis.set(name=name, value=payload.model_dump_json())
        print("SET", response)
        response = await redis.xadd(
            name="ol:events",
            fields={
                "name": workflow.TYPE,
                "scheme": workflow.SCHEMA,
                "job_id": "test-uuid",
                "status": WorkflowState.PENDING.value,
            },
        )
        print("XADD", response)

    @asynccontextmanager
    async def start(self):
        self.task = asyncio.create_task(self._run_())
        yield
        self.event.set()
        await asyncio.gather(self.task)
        print("Worker Exited.")


@rx.event
async def add_event(_: rx.State):
    await Worker.create_workflow(
        workflow=LXCCreateV1,
        payload=LXCCreateV1.PAYLOAD(
            state=WorkflowState.PENDING,
            compute_type="lxc",
            manifest="test-lxc-manifest",
        ),
    )


@rx.page("/")
def home() -> rx.Component:
    """Home page that displays either the main dashboard or splash page based on configuration status."""
    return rx.cond(
        SplashPageState.initialization_state == InitializationState.COMPLETE,
        rx.el.div(
            components.SideBar(
                components.SideBar.NavItem(icon="server", text="Proxmox Nodes", href="/nodes"),
                components.SideBar.NavItem(icon="server-cog", text="Compute", href="/compute"),
                components.SideBar.NavItem(icon="book-lock", text="Secrets & PKI", href="/secrets-pki"),
                components.SideBar.NavItem(icon="network", text="Sectors", href="/sectors"),
            ),
            rx.el.div(
                rx.el.div(
                    components.Buttons.Primary("Add Event", on_click=add_event),
                ),
                class_name=(
                    "min-h-screen w-full flex flex-col p-4 "
                    "bg-gradient-to-b from-gray-200 to-gray-400 "
                    "dark:from-[#111317] dark:to-[#151820] "
                    "text-gray-800 dark:text-[#E8F1FF] "
                    "selection:bg-[#36E2F4]/40 selection:text-white "
                    "backdrop-blur-sm transition-colors duration-300 ease-in-out"
                ),
            ),
            class_name="min-h-screen w-full flex",
        ),
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


# class OrbitLabWorker:
#     def __init__(self) -> None:
#         self.redis = Redis(host="192.168.87.230", port=6379)
#         response = await self.redis.xadd(name="ol:events", fields={"event_name": "ol.init"})
#         print(response)
#         try:
#             response = await self.redis.xgroup_create(name="ol:events", groupname="ol:workers")
#             print(response)
#         except exceptions.ResponseError as err:
#             if "BUSYGROUP Consumer Group name already exists" in err.args:
#                 pass
#             else:
#                 raise RuntimeError from err

# OrbitLabWorker()

app = rx.App(
    stylesheets=["animations.css"],
    api_transformer=Starlette(
        routes=[
            WebSocketRoute("/ws/terminal/{compute_type}/{vmid}", endpoint=TerminalProxy),
        ],
    ),
)
app.register_lifespan_task(Worker().start)
