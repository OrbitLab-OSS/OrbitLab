"""Reusable NiceGUI components that preserve OrbitLab's visual language."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from nicegui import ui


@dataclass(slots=True)
class PageHeader:
    """A consistent page title and manual-refresh action."""

    title: str
    subtitle: str = ""
    refresh: Callable[[], Awaitable[None]] | None = None

    def render(self) -> None:
        """Render the header."""
        with ui.row().classes("w-full items-center justify-between gap-4 mb-6"):
            with ui.column().classes("gap-1"):
                ui.label(self.title).classes("text-2xl font-bold tracking-tight text-[#E8F1FF]")
                if self.subtitle:
                    ui.label(self.subtitle).classes("ol-muted text-sm")
            if self.refresh:
                ui.button("Refresh", icon="refresh", on_click=self.refresh).props("outline dense no-caps").classes("text-[#7DECF8]")


@dataclass(slots=True)
class StatusBadge:
    """Small semantic status badge used in inventory rows and cards."""

    value: str

    def render(self) -> None:
        """Render a color based on the status text without coupling to an enum."""
        normalized = self.value.lower()
        color = "positive" if any(word in normalized for word in ("online", "running", "available", "healthy", "configured")) else "negative" if any(word in normalized for word in ("offline", "failed", "unhealthy")) else "warning"
        ui.badge(self.value.replace("_", " ").title(), color=color).props("outline").classes("font-medium")


@dataclass(slots=True)
class InventoryTable:
    """A refreshable four-column inventory that prioritizes human-readable data."""

    title: str
    rows_loader: Callable[[], Awaitable[list[dict[str, str]]]]
    empty_message: str
    open_row: Callable[[dict[str, str]], None] | None = None
    rows: list[dict[str, str]] = field(default_factory=list)

    @ui.refreshable_method
    async def render(self) -> None:
        """Fetch and render the current inventory snapshot."""
        self.rows = await self.rows_loader()
        if not self.rows:
            with ui.card().classes("ol-card w-full p-8 text-center"):
                ui.icon("inventory_2", size="2rem").classes("text-[#36E2F4] mx-auto")
                ui.label(self.empty_message).classes("ol-muted mt-2")
            return
        columns = [
            {"name": "name", "label": "Name", "field": "name", "align": "left", "sortable": True},
            {"name": "status", "label": "Status", "field": "status", "align": "left", "sortable": True},
            {"name": "location", "label": "Location", "field": "location", "align": "left", "sortable": True},
            {"name": "detail", "label": "Details", "field": "detail", "align": "left"},
        ]
        if self.open_row:
            columns.append({"name": "open", "label": "", "field": "open", "align": "right"})
        table = ui.table(columns=columns, rows=self.rows, row_key="name", pagination=10).classes("ol-table ol-card w-full")
        table.add_slot("body-cell-status", """
            <q-td :props="props"><q-badge outline :color="props.value.toLowerCase().match(/online|running|available|healthy|configured/) ? 'positive' : props.value.toLowerCase().match(/offline|failed|unhealthy/) ? 'negative' : 'warning'">{{ props.value }}</q-badge></q-td>
        """)
        if self.open_row:
            table.add_slot("body-cell-open", """
                <q-td :props="props"><q-btn flat dense round icon="open_in_new" color="secondary" @click="$parent.$emit('orbitlab-open', props.row)" /></q-td>
            """)
            table.on("orbitlab-open", lambda event: self.open_row(event.args))


@dataclass(slots=True)
class DetailView:
    """A readable resource page built from the UI detail contract."""

    status: str
    sections: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]

    def render(self) -> None:
        """Render resource facts in small cards rather than a raw model dump."""
        StatusBadge(self.status).render()
        with ui.row().classes("w-full gap-4 flex-wrap mt-5"):
            for title, values in self.sections:
                with ui.card().classes("ol-card p-5 min-w-[280px] flex-1"):
                    ui.label(title).classes("text-base font-semibold mb-3")
                    for label, value in values:
                        with ui.row().classes("w-full items-start justify-between gap-4 py-1"):
                            ui.label(label).classes("ol-muted text-sm")
                            ui.label(value).classes("text-sm text-right break-all")


@dataclass(slots=True)
class ApplicationShell:
    """The persistent OrbitLab navigation and content frame."""

    active_path: str

    NAVIGATION = (
        ("Overview", "home", "/"),
        ("Setup", "rocket_launch", "/setup"),
        ("Nodes", "dns", "/nodes"),
        ("Compute", "memory", "/compute"),
        ("Sectors", "hub", "/sectors"),
        ("DataCore", "database", "/datacore"),
        ("DockFS", "storage", "/dock-fs"),
        ("Conduit", "route", "/conduit"),
        ("Templates", "inventory_2", "/compute/appliances"),
        ("Secrets & PKI", "key", "/secrets-pki"),
        ("Activity", "receipt_long", "/activity"),
        ("Settings", "settings", "/settings"),
    )

    def render(self) -> None:
        """Render the layout container and keep a content context open to the caller."""
        raise RuntimeError("Use ApplicationShell.content() as a context manager.")

    def content(self):
        """Return a context manager for the current page content."""
        shell = self

        class _ShellContent:
            def __enter__(self) -> None:
                with ui.left_drawer(value=True).classes("ol-sidebar"):
                    with ui.row().classes("items-center gap-3 p-4"):
                        ui.icon("orbit", size="2rem").classes("text-[#36E2F4]")
                        ui.label("OrbitLab").classes("text-lg font-bold tracking-wide")
                    with ui.column().classes("w-full gap-1 px-2"):
                        for label, icon, path in shell.NAVIGATION:
                            classes = "w-full justify-start no-caps " + ("ol-nav-active" if path == shell.active_path else "text-[#AEB9CC]")
                            ui.button(label, icon=icon, on_click=lambda target=path: ui.navigate.to(target)).props("flat").classes(classes)
                self._page = ui.column().classes("ol-page w-full min-h-screen p-6 lg:p-8")
                self._page.__enter__()

            def __exit__(self, exc_type, exc_value, traceback) -> None:
                self._page.__exit__(exc_type, exc_value, traceback)

        return _ShellContent()
