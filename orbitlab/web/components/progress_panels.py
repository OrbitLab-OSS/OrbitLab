"""OrbitLab Progress Panel component."""

import reflex as rx

from orbitlab.web.states.utilities import EventGroup

from .buttons import Buttons


class ProgressPanelStateManager(rx.State):
    """Manages the state of progress panels including step tracking and registration."""

    registered: rx.Field[dict[str, int]] = rx.field(default_factory=dict)

    @rx.event
    async def register(self, progress_id: str) -> None:
        """Register a new progress panel with the given ID."""
        self.registered[progress_id] = 0


class ProgressStep:
    """Represents a single step in a progress panel workflow."""

    def __init__(self, name: str, *children: rx.Component, validate: rx.EventHandler) -> None:
        """Initialize a progress step with a name, child components, and validation handler."""
        self.name = name
        self.children = children
        self.validate = validate

    def __apply_form__(self, component: rx.Component, form: str) -> None:
        """Recursively apply form attribute to component and its children."""
        if hasattr(component, "name") and isinstance(component.name, str | rx.vars.LiteralStringVar):
            component.custom_attrs["form"] = form
        for child in component.children:
            self.__apply_form__(child, form)

    def get_component(self, progress_id: str, index: int, steps: int, cancel_button: rx.Component) -> rx.Component:
        """Generate the component for this progress step with navigation buttons."""
        form = f"{progress_id}-form-{index}"
        for child in self.children:
            self.__apply_form__(child, form)
        return rx.el.div(
            rx.el.form(id=form, on_submit=self.validate),
            *self.children,
            rx.el.div(
                rx.match(
                    ProgressPanelStateManager.registered.get(progress_id, 0),
                    (
                        0,
                        rx.fragment(cancel_button, Buttons.Primary("Next", form=form)),
                    ),
                    (
                        steps - 1,
                        rx.fragment(
                            cancel_button,
                            Buttons.Secondary("Previous", on_click=ProgressPanels.previous(progress_id)),
                            Buttons.Primary("Submit", form=form),
                        ),
                    ),
                    rx.fragment(
                        cancel_button,
                        Buttons.Secondary("Previous", on_click=ProgressPanels.previous(progress_id)),
                        Buttons.Primary("Next", form=form),
                    ),
                ),
                class_name="w-full flex justify-end space-x-2 mt-10",
            ),
            data_active=ProgressPanelStateManager.registered.get(progress_id, 0) == index,
            class_name="w-full flex flex-col data-[active=false]:hidden",
        )


class ProgressPanels(EventGroup):
    """A component class for creating multi-step progress panels with navigation.

    This class provides methods for managing progress panel state transitions
    and rendering step-based workflows with navigation controls.
    """

    @staticmethod
    @rx.event
    async def next(state: ProgressPanelStateManager, progress_id: str) -> None:
        """Advance the progress panel to the next step."""
        state.registered[progress_id] += 1

    @staticmethod
    @rx.event
    async def previous(state: ProgressPanelStateManager, progress_id: str) -> None:
        """Move the progress panel to the previous step."""
        state.registered[progress_id] -= 1

    @staticmethod
    @rx.event
    async def reset(state: ProgressPanelStateManager, progress_id: str) -> None:
        """Reset the progress panel to the first step."""
        state.registered[progress_id] = 0

    Step = staticmethod(ProgressStep)

    @classmethod
    def __step_icon__(cls, progress_id: str, index: int) -> rx.Component:
        """Return the circular step indicator depending on step state."""
        return rx.cond(
            ProgressPanelStateManager.registered.get(progress_id, 0) > index,
            rx.el.div(
                rx.icon("check", size=14, class_name="text-white"),
                class_name=(
                    "flex items-center justify-center w-6 h-6 rounded-full "
                    "bg-[#1E63E9] dark:bg-[#36E2F4] "
                    "shadow-[0_0_6px_rgba(54,226,244,0.4)]"
                ),
            ),
            rx.cond(
                ProgressPanelStateManager.registered.get(progress_id, 0) == index,
                rx.el.div(
                    f"{index + 1}",
                    class_name=(
                        "flex items-center justify-center w-6 h-6 rounded-full "
                        "text-white font-semibold "
                        "bg-gradient-to-r from-[#1E63E9] to-[#36E2F4] "
                        "shadow-[0_0_8px_rgba(54,226,244,0.5)]"
                    ),
                ),
                rx.el.div(
                    f"{index + 1}",
                    class_name=(
                        "flex items-center justify-center w-6 h-6 rounded-full "
                        "text-gray-400 dark:text-gray-600 "
                        "bg-gray-200/70 dark:bg-white/[0.05]"
                    ),
                ),
            ),
        )

    @classmethod
    def __step_panel__(cls, progress_id: str, title: str, step_count: int, index: int) -> rx.Component:
        """Create and return the panel component."""
        return rx.fragment(
            rx.el.div(
                rx.el.div(
                    cls.__step_icon__(progress_id, index),
                    class_name="flex-shrink-0",
                ),
                rx.el.div(
                    rx.el.p(
                        title,
                        data_active=ProgressPanelStateManager.registered.get(progress_id, 0) == index,
                        class_name=(
                            "text-sm font-medium text-gray-600 dark:text-gray-400 data-[active=true]:text-[#1E63E9] "
                            "data-[active=true]:dark:text-[#36E2F4]"
                        ),
                    ),
                    class_name="ml-4",
                ),
                class_name="flex items-center",
            ),
            rx.cond(
                index == step_count - 1,
                rx.fragment(),
                rx.el.div(
                    data_active=ProgressPanelStateManager.registered.get(progress_id, 0) > index,
                    class_name=(
                        "h-8 w-[2px] rounded-full bg-[#1E63E9]/50 dark:bg-[#36E2F4]/50 "
                        "data-[active=true]:bg-gray-300 data-[active=true]:dark:bg-white/[0.06]"
                    ),
                ),
            ),
        )

    @classmethod
    def __new__(cls, *steps: ProgressStep, progress_id: str, cancel_button: rx.Component | None = None) -> rx.Component:
        """Render the full vertical progress panel."""
        steps = [step for step in steps if isinstance(step, ProgressStep)]
        titles = [step.name for step in steps]
        cancel_button = cancel_button or rx.fragment()
        return rx.el.div(
            rx.el.div(
                rx.foreach(
                    titles,
                    lambda title, index: cls.__step_panel__(progress_id, title, len(titles), index),
                ),
                class_name=(
                    "relative flex gap-3 justify-evenly "
                    "p-4 rounded-xl "
                    "border border-gray-200 dark:border-white/[0.08] "
                    "bg-gradient-to-b from-white/90 to-gray-100/70 "
                    "dark:from-[#0E1015]/80 dark:to-[#181B22]/80 "
                    "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)] "
                    "hover:ring-1 hover:ring-[#36E2F4]/30 "
                    "backdrop-blur-sm transition-all duration-300 ease-in-out"
                ),
            ),
            rx.el.div(
                *[
                    step.get_component(
                        progress_id=progress_id,
                        index=index,
                        steps=len(steps),
                        cancel_button=cancel_button,
                    )
                    for index, step in enumerate(steps)
                ],
                class_name="px-6 py-3",
            ),
            on_mount=ProgressPanelStateManager.register(progress_id),
            class_name="min-w-[600px]",
        )
