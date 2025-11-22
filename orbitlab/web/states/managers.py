import reflex as rx


class ProgressPanelStateManager(rx.State):
    registered: dict[str, int] = rx.field(default_factory=dict)

    @rx.event
    async def register(self, progress_id: str) -> None:
        self.registered[progress_id] = 0

    @rx.event
    async def next(self, progress_id: str) -> None:
        self.registered[progress_id] += 1

    @rx.event
    async def previous(self, progress_id: str) -> None:
        self.registered[progress_id] -= 1

    @rx.event
    async def reset_progress(self, progress_id: str) -> None:
        self.registered[progress_id] = 0
