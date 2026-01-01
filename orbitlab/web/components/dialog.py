"""Dialog component factory for creating modal dialogs."""

from typing import TypedDict, Unpack

import reflex as rx

from orbitlab.web.utilities import EventGroup


class DialogStateManager(rx.State):
    """State manager for tracking dialog open/close states."""

    registered: rx.Field[dict[str, bool]] = rx.field(default_factory=dict)

    @rx.event
    async def register(self, dialog_id: str) -> None:
        """Register a dialog."""
        self.registered[dialog_id] = False


class DialogProps(TypedDict, total=False):
    """Dialog Component Props."""

    on_open: rx.EventHandler | rx.event.EventCallback | list[rx.EventHandler | rx.event.EventCallback]
    on_close: rx.EventHandler | rx.event.EventCallback | list[rx.EventHandler | rx.event.EventCallback]
    class_name: str


class Dialog(EventGroup):
    """A factory class for creating dialog components."""

    @staticmethod
    @rx.event
    async def open(state: DialogStateManager, dialog_id: str) -> None:
        """Open a dialog by setting its state to True."""
        state.registered[dialog_id] = True

    @staticmethod
    @rx.event
    async def close(state: DialogStateManager, dialog_id: str) -> None:
        """Close a dialog by setting its state to False."""
        state.registered[dialog_id] = False

    def __new__(cls, title: str, *children: rx.Component, dialog_id: str, **props: Unpack[DialogProps]) -> rx.Component:
        """Create a new dialog component instance."""
        on_open = props.pop("on_open", None)
        on_close = props.pop("on_close", None)
        class_name = props.get("class_name", "max-w-[50vw] w-[50vw] max-h-[50vh] h-[50vh]")
        props["class_name"] = f"flex flex-col {class_name}"
        return rx.dialog.root(
            rx.dialog.content(
                rx.dialog.title(title),
                *children,
                on_open_auto_focus=on_open,  # pyright: ignore[reportArgumentType]
                on_close_auto_focus=on_close,  # pyright: ignore[reportArgumentType]
                **props,
            ),
            on_mount=DialogStateManager.register(dialog_id),
            open=DialogStateManager.registered.get(dialog_id, False).to(bool),
            class_name=(
                "border-r border-gray-200 dark:border-white/[0.08] "
                "transition-all duration-300 ease-in-out "
                "bg-gradient-to-b from-gray-50/95 to-gray-200/80 "
                "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)] "
                "hover:ring-1 hover:ring-[#36E2F4]/30"
            ),
        )
