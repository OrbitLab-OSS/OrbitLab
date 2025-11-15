import reflex as rx


class DialogStateManager(rx.State):
    registered: dict[str, bool] = rx.field(default_factory=dict)

    @rx.event
    async def register(self, dialog_id: str) -> None:
        self.registered[dialog_id] = False

    @rx.event
    async def toggle(self, dialog_id: str) -> None:
        self.registered[dialog_id] = not self.registered[dialog_id]

    @rx.event
    async def close(self, dialog_id: str) -> None:
        self.registered[dialog_id] = False


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
