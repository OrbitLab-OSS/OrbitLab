"""NiceGUI entry point for OrbitLab."""

from __future__ import annotations

from contextlib import AsyncExitStack

from nicegui import app, ui

from orbitlab.ui.pages import register_routes
from orbitlab.ui.state import Clients
from orbitlab.ui.styles import OrbitLabTheme
from orbitlab.worker import Worker


class OrbitLabApplication:
    """Owns NiceGUI startup resources and keeps UI/worker lifecycles separate."""

    def __init__(self) -> None:
        self.clients = Clients()
        self.worker = Worker()
        self._worker_lifecycle = AsyncExitStack()

    async def start(self) -> None:
        """Start Redis-backed services without coupling workers to the UI."""
        await self._worker_lifecycle.enter_async_context(self.worker.start())

    async def stop(self) -> None:
        """Stop worker execution before releasing its shared infrastructure."""
        await self._worker_lifecycle.aclose()
        await self.clients.close()


def create_application() -> OrbitLabApplication:
    """Configure the NiceGUI app and return its lifecycle owner."""
    OrbitLabTheme.install()
    application = OrbitLabApplication()
    register_routes(application.clients)
    app.on_startup(application.start)
    app.on_shutdown(application.stop)
    return application


application = create_application()


def main() -> None:
    """Run the OrbitLab NiceGUI server."""
    ui.run(title="OrbitLab", dark=True, reload=False, show=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()
