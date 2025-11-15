"""Dialog component factory for creating modal dialogs."""

import reflex as rx

from orbitlab.web.states.managers import DialogStateManager


class Dialog:
    """A factory class for creating dialog components.

    This class creates a reflex dialog component with a title, content,
    and automatic state management for open/close behavior.
    """

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
