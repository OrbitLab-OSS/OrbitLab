"""Workflow feed component for custom LXC appliance creation."""
import reflex as rx

from orbitlab.web.states.utilities import EventGroup


class WorkflowFeedStep:
    """Single step in the LXC workflow feed."""

    def __new__(cls, title: str, description: str, status: str) -> rx.Component:
        icon_map = {
            "pending": "clock",
            "running": "loader-2",
            "complete": "check-circle-2",
            "failed": "x-circle",
        }
        color_map = {
            "pending": "text-gray-400 dark:text-gray-500",
            "running": "text-[#36E2F4]",
            "complete": "text-green-500",
            "failed": "text-red-500",
        }

        return rx.el.li(
            rx.el.div(
                rx.icon(icon_map.get(status, "dot"), class_name=f"w-5 h-5 {color_map.get(status, '')}"),
                class_name="flex-shrink-0",
            ),
            rx.el.div(
                rx.el.h4(title, class_name="text-sm font-semibold text-gray-900 dark:text-[#E8F1FF]"),
                rx.el.p(description, class_name="text-xs text-gray-600 dark:text-gray-400"),
                class_name="ml-4",
            ),
            class_name="flex items-start gap-2 py-3",
        )


class WorkflowFeed(EventGroup):
    def __new__(cls, steps: list[dict]) -> rx.Component:
        return rx.el.div(
            rx.el.ul(
                rx.foreach(steps, lambda step: WorkflowFeedStep(step["title"], step["description"], step["status"])),
                class_name="divide-y divide-gray-200 dark:divide-white/[0.08]",
            ),
            class_name="max-w-xl w-full",
        )
