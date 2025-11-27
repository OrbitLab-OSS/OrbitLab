"""Dialog component factory for creating modal dialogs."""

import reflex as rx


class DialogStateManager(rx.State):
    """State manager for tracking dialog open/close states."""
    registered: dict[str, bool] = rx.field(default_factory=dict)

    @rx.event
    async def register(self, dialog_id: str) -> None:
        """Register a dialog."""
        self.registered[dialog_id] = False


@rx.event
async def open_dialog(state: DialogStateManager, dialog_id: str) -> None:
    """Open a dialog by setting its state to True."""
    state.registered[dialog_id] = True


@rx.event
async def close_dialog(state: DialogStateManager, dialog_id: str) -> None:
    """Close a dialog by setting its state to False."""
    state.registered[dialog_id] = False


class Dialog:
    """A factory class for creating dialog components.

    This class creates a reflex dialog component with a title, content,
    and automatic state management for open/close behavior.
    """

    open = staticmethod(open_dialog)
    close = staticmethod(close_dialog)

    def __new__(cls, title: str, *children: rx.Component, dialog_id: str, **props: dict) -> rx.Component:
        """Create a new dialog component instance.

        Args:
            title: The title of the dialog.
            *children: The content components to display in the dialog.
            dialog_id: A unique identifier for the dialog used for state management.
            **props: Additional properties, including optional 'class_name' for styling.

        Returns:
            A configured dialog root component.
        """
        class_name = props.pop("class_name", "max-w-[50vw] w-[50vw] max-h-[50vh] h-[50vh]")
        return rx.dialog.root(
            rx.dialog.content(
                rx.dialog.title(title),
                *children,
                class_name=f"flex flex-col {class_name}",
            ),
            on_mount=DialogStateManager.register(dialog_id),
            open=DialogStateManager.registered.get(dialog_id, False),
            class_name=(
                "border-r border-gray-200 dark:border-white/[0.08] "
                "transition-all duration-300 ease-in-out "
                "bg-gradient-to-b from-gray-50/95 to-gray-200/80 "
                "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)] "
                "hover:ring-1 hover:ring-[#36E2F4]/30"
            ),
        )
