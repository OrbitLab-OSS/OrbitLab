"""Progress bar components for the OrbitLab web application."""

from types import SimpleNamespace

import reflex as rx


class Basic:
    """OrbitLab-themed progress bar with glow, gradients, and theme-aware styling."""

    def __new__(
        cls,
        value: float | rx.Var[float],
        *,
        maximum: float = 100,
        show_label: bool = True,
    ) -> rx.Component:
        """Create an OrbitLab-styled progress bar.

        Args:
            value: Current progress value (between 0 and max).
            maximum: Maximum progress value (default 100).
            show_label: Whether to show the percentage label below the bar.
        """
        percent = rx.cond(maximum > 0, (value / maximum) * 100, 0)
        return rx.el.div(
            rx.el.div(
                rx.progress(
                    value=value,
                    max=maximum,
                    class_name=(
                        # === Base bar track ===
                        "w-full h-3 rounded-full overflow-hidden "
                        "bg-gray-200/70 dark:bg-white/[0.07] backdrop-blur-sm "
                        "outline outline-1 outline-gray-200/50 dark:outline-white/[0.05] "
                        "shadow-[inset_0_1px_2px_rgba(0,0,0,0.15)] "
                        # === Progress fill ===
                        "[&::-webkit-progress-value]:transition-all [&::-webkit-progress-value]:duration-500 "
                        "[&::-webkit-progress-value]:ease-in-out "
                        "[&::-webkit-progress-value]:bg-gradient-to-r "
                        "[&::-webkit-progress-value]:from-[#1E63E9] "
                        "[&::-webkit-progress-value]:to-[#36E2F4] "
                        "[&::-webkit-progress-value]:shadow-[0_0_6px_rgba(54,226,244,0.4)] "
                        "[&::-moz-progress-bar]:bg-gradient-to-r "
                        "[&::-moz-progress-bar]:from-[#1E63E9] "
                        "[&::-moz-progress-bar]:to-[#36E2F4]"
                    ),
                ),
                class_name="relative w-full",
            ),
            rx.cond(
                show_label,
                rx.text(
                    f"{percent:.1f}%",
                    class_name=("mt-2 text-xs font-medium text-gray-600 dark:text-gray-400 tracking-wide select-none"),
                ),
            ),
            class_name="flex justify-start items-center w-full transition-all duration-300 ease-in-out",
        )


class ProgressBars(SimpleNamespace):
    """Namespace container for progress bar component classes."""

    Basic = staticmethod(Basic)
