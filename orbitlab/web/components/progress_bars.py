"""Progress bar components for the OrbitLab web application."""
from types import SimpleNamespace

import reflex as rx


class Basic:
    """A basic progress bar component.

    This class provides a factory for creating styled progress bar components
    with optional labels and status text. Progress bars support light and dark themes
    with smooth transitions and tooltip display of progress percentage.
    """

    @classmethod
    def __step_labels__(cls, label: str) -> rx.Component:
        """Create a step label component with appropriate styling.

        Args:
            label: The text label to display.

        Returns:
            A Reflex component representing the styled label.
        """
        return rx.el.div(
            label,
            class_name="text-gray-600 dark:text-gray-400 not-first:text-center last:text-right",
        )

    def __new__(
        cls,
        progress: float | rx.Var[float],
        start_label: str = "",
        end_label: str = "",
        status: str | None = None,
    ) -> rx.Component:
        """Create a basic progress bar component.

        Args:
            progress: The progress value as a percentage (0-100).
            start_label: Label displayed at the start of the progress bar.
            end_label: Label displayed at the end of the progress bar.
            status: Optional status text displayed above the progress bar.

        Returns:
            A Reflex component representing the progress bar.
        """
        return rx.el.div(
            rx.cond(
                status,
                rx.el.p(
                    status,
                    class_name="text-sm font-medium text-gray-900 dark:text-[#E8F1FF]",
                ),
            ),
            rx.el.div(
                rx.tooltip(
                    rx.el.div(
                        rx.el.div(
                            style={"width": f"{progress:.1f}%"},
                            class_name=(
                                "h-2 rounded-full "
                                "bg-[#1E63E9] dark:bg-[#36E2F4] "
                                "shadow-[0_0_6px_rgba(54,226,244,0.4)] "
                                "transition-all duration-500 ease-in-out"
                            ),
                        ),
                        class_name=(
                            "overflow-hidden rounded-full "
                            "bg-gray-200/70 dark:bg-white/[0.07] "
                            "backdrop-blur-sm"
                        ),
                    ),
                    content=f"{progress:.1f}%",
                ),
                rx.el.div(
                    rx.el.div(
                        start_label,
                        class_name="text-gray-600 dark:text-gray-400 not-first:text-center last:text-right",
                    ),
                    rx.el.div(
                        end_label,
                        class_name="text-gray-600 dark:text-gray-400 not-first:text-center last:text-right",
                    ),
                    class_name="w-full flex justify-between",
                ),
            ),
            aria_hidden="true",
            class_name="mt-6",
        )


class ProgressBarsNamespace(SimpleNamespace):
    """Namespace container for progress bar component classes."""

    Basic = Basic


ProgressBars = ProgressBarsNamespace()
