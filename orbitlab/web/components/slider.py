"""OrbitLab Range Slider Component."""

import uuid
from types import NoneType
from typing import TypedDict, Unpack

import reflex as rx

from orbitlab.web.utilities import EventGroup


class SliderStateManager(rx.State):
    """State manager for slider components."""

    registered: rx.Field[dict[str, list[float]]] = rx.field(default_factory=dict)

    @rx.event
    async def register(self, slider_id: str, default_value: float | list[float]) -> None:
        """Register a slider."""
        self.registered[slider_id] = default_value if isinstance(default_value, list | tuple) else [default_value]


class SliderProps(TypedDict, total=False):
    """Slider Component Props."""

    default_value: float | rx.Var[float | list[float]]
    min: int
    max: int
    required: bool
    name: str
    form: str


class Slider(EventGroup):
    """OrbitLab-themed slider component (Radix-based)."""

    text_class = "min-w-[2.5rem] text-right text-sm font-semibold text-gray-800 dark:text-[#E8F1FF]"

    @staticmethod
    @rx.event
    async def set_value(state: SliderStateManager, slider_id: str, value: list[float]) -> None:
        """Set the value for a registered slider for display purposes only."""
        state.registered[slider_id] = value

    def __new__(cls, **props: Unpack[SliderProps]) -> rx.Component:
        """Create and return the slider component."""
        default_value = props.get("default_value")
        if isinstance(default_value, NoneType):
            default_value = props.get("min", 0)
        slider_id = str(uuid.uuid4())
        on_change = props.pop("on_change", rx.prevent_default)
        return rx.el.div(
            rx.text(
                SliderStateManager.registered.get(slider_id, [1]).to(list)[0],
                class_name=cls.text_class,
            ),
            rx.slider(
                class_name=(
                    # Layout
                    "relative flex w-full items-center select-none "
                    # Smooth theme transitions
                    "transition-all duration-300 "
                    # 🟦 Track
                    "[&_.rt-SliderTrack]:h-2 "
                    "[&_.rt-SliderTrack]:w-full "
                    "[&_.rt-SliderTrack]:rounded-full "
                    # Chrome background
                    "[&_.rt-SliderTrack]:bg-gray-200/70 "
                    "dark:[&_.rt-SliderTrack]:bg-white/[0.07] "
                    "[&_.rt-SliderTrack]:backdrop-blur-sm "
                    "[&_.rt-SliderTrack]:shadow-[inset_0_0_1px_rgba(255,255,255,0.15)] "
                    # 🟦 Range fill
                    "[&_.rt-SliderRange]:h-full "
                    "[&_.rt-SliderRange]:rounded-full "
                    # OrbitLab glow
                    "[&_.rt-SliderRange]:bg-[#1E63E9] "
                    "dark:[&_.rt-SliderRange]:bg-[#36E2F4] "
                    "[&_.rt-SliderRange]:shadow-[0_0_10px_rgba(54,226,244,0.35)] "
                    "transition-all duration-300 "
                    # 🟦 Thumb
                    "[&_.rt-SliderThumb]:w-5 [&_.rt-SliderThumb]:h-5 "
                    "[&_.rt-SliderThumb]:rounded-full "
                    # Chrome glass
                    "[&_.rt-SliderThumb]:bg-white "
                    "dark:[&_.rt-SliderThumb]:bg-[#0E1015] "
                    "[&_.rt-SliderThumb]:border "
                    "[&_.rt-SliderThumb]:border-gray-300 "
                    "dark:[&_.rt-SliderThumb]:border-white/[0.25] "
                    "[&_.rt-SliderThumb]:backdrop-blur-sm "
                    # Glow + hover
                    "[&_.rt-SliderThumb]:shadow-[0_0_6px_rgba(54,226,244,0.35)] "
                    "[&_.rt-SliderThumb]:transition-all [&_.rt-SliderThumb]:duration-300 "
                    "[&_.rt-SliderThumb]:hover:scale-110 "
                    "[&_.rt-SliderThumb]:hover:shadow-[0_0_12px_rgba(54,226,244,0.55)] "
                    "[&_.rt-SliderThumb]:active:scale-95 "
                ),
                id=slider_id,
                on_change=lambda value: [cls.set_value(slider_id, value), on_change],
                on_mount=SliderStateManager.register(slider_id, default_value),
                **props,
            ),
            rx.cond(
                SliderStateManager.registered.get(slider_id, []).to(list).length() > 1,
                rx.text(
                    SliderStateManager.registered.get(slider_id, [0, 1]).to(list)[1],
                    class_name=cls.text_class,
                ),
            ),
            class_name="w-full flex items-center space-x-3",
        )
