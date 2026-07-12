"""OrbitLab Web UI."""

import reflex as rx
from reflex.middleware import Middleware
from reflex_base.event import get_hydrate_event
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute

from orbitlab.data_types import InitializationStatus
from orbitlab.redis.clients import ClusterClient, PKIClient
from orbitlab.web.global_state import InfrastructureManagementState, OrbitLabState, SelectionDefaults
from orbitlab.web.pages import *
from orbitlab.web.utilities import TerminalProxy
from orbitlab.worker import Worker


class OrbitLabMiddleware(Middleware):
    async def preprocess(self, app, state, event) -> None:
        if event.name != get_hydrate_event(state):
            return None

        if await ClusterClient().is_initialized():
            orbitlab_state = await state.get_state(OrbitLabState)
            orbitlab_state.status = InitializationStatus.COMPLETE
            orbitlab_state.root_certificates = await PKIClient().list_root_certificates()
            self.intermediate_certificates = await PKIClient().list_intermediate_certificates()
            self.leaf_certificates = await PKIClient().list_leaf_certificates()
            
            infra_state = await state.get_state(InfrastructureManagementState)
            infra_state.infra = await ClusterClient().get_infra_appliances()
            
            defaults_state = await state.get_state(SelectionDefaults)
            defaults_state.defaults = await ClusterClient().get_defaults()
        else:
            orbitlab_state = await state.get_state(OrbitLabState)
            orbitlab_state.status = InitializationStatus.NOT_STARTED


app = rx.App(
    stylesheets=["animations.css"],
    api_transformer=Starlette(
        routes=[
            WebSocketRoute("/ws/terminal/{vmid}", endpoint=TerminalProxy),
        ],
    ),
)
app.register_lifespan_task(Worker().start)
app.add_middleware(OrbitLabMiddleware())
