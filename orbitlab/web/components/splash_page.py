import random

import reflex as rx

from orbitlab.data_types import InitializationStatus
from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState
from orbitlab.web.components.initializer import InitializationDialogs, InitializationState


class SplashPage:
    def __new__(cls) -> rx.Component:
        return rx.box(
            rx.box(
                rx.el.svg(
                    *[
                        rx.el.circle(
                            cx=f"{x}%",
                            cy=f"{y}%",
                            r=f"{r:.1f}",
                            fill="#E8F1FF",
                            opacity="0",
                            style={"--dx": str(y), "--dy": str(x), "--duration": f"{duration}s"},
                            class_name="star",
                        )
                        for x, y, r, duration in [
                            (
                                random.randint(1, 99),  # noqa: S311
                                random.randint(1, 99),  # noqa: S311
                                random.uniform(0.1, 2.1),  # noqa: S311
                                random.randint(5, 15),  # noqa: S311
                            )
                            for _ in range(random.randint(15, 20))  # noqa: S311
                        ]
                    ],
                    xmlns="http://www.w3.org/2000/svg",
                    viewBox="0 0 200 200",
                    fill="none",
                    class_name="w-full h-full",
                ),
                class_name="absolute inset-0",
            ),
            tailwind.OrbitLabLogo(size=150, animated=True),
            rx.box(
                rx.text(
                    "OrbitLab",
                    class_name="text-[#E8F1FF] font-semibold tracking-widest text-2xl mt-8 fade-title",
                ),
                rx.match(
                    OrbitLabState.status,
                    (
                        InitializationStatus.UNKNOWN,
                        rx.text("Loading...",  class_name="text-[#36E2F4] text-sm mt-2 fade-subtitle")
                    ),
                    (
                        InitializationStatus.NOT_STARTED,
                        tailwind.Buttons.Primary(
                            "Initialize",
                            on_click=InitializationDialogs.initialize,
                            class_name="z-10 mt-2 fade-subtitle"
                        ),
                    ),
                    (
                        InitializationStatus.IN_PROGRESS,
                        rx.text(InitializationState.progress_message,  class_name="text-[#36E2F4] text-sm mt-2 fade-subtitle")
                    ),
                ),
                class_name="flex flex-col items-center justify-center",
            ),
            InitializationDialogs(),
            class_name=(
                "relative flex flex-col items-center justify-center min-h-screen w-full "
                "bg-[#0E1015] overflow-hidden select-none"
            ),
        )
