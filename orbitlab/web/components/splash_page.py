"""Splash page component for OrbitLab, displaying animated SVG graphics and initialization text."""

import random

import reflex as rx


class SplashPage:
    """A splash page component for OrbitLab, displaying animated SVG graphics and initialization text."""

    def __new__(cls) -> rx.Component:
        """Create and return the SplashPage component with animated SVG graphics and initialization text."""
        return rx.box(
            rx.box(
                rx.el.svg(
                    *[
                        rx.el.circle(
                            cx=f"{x}%", cy=f"{y}%", r=f"{r:.1f}",
                            fill="#E8F1FF",
                            opacity="0",
                            style={"--dx":str(y), "--dy":str(x), "--duration": f"{duration}s"},
                            class_name="star",
                        )
                        for x, y, r, duration in [
                            (
                                random.randint(1, 99),  # noqa: S311
                                random.randint(1, 99),  # noqa: S311
                                random.uniform(0.1, 2.1),  # noqa: S311
                                random.randint(2,12),  # noqa: S311
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
            rx.box(
                rx.box(
                    class_name="orbit-dot",
                ),
                rx.box(
                    position="absolute",
                    top="35%",
                    left="35%",
                    width="14px",
                    height="14px",
                    border_radius="50%",
                    background_color="#4F8BF9",
                    filter="drop-shadow(0 0 6px #4F8BF9)",
                ),
                rx.el.svg(
                    rx.el.defs(
                        rx.el.radial_gradient(
                            rx.el.stop(offset="0%", stop_color="#36E2F4", stop_opacity="0.8"),
                            rx.el.stop(offset="100%", stop_color="#0E1015", stop_opacity="0"),
                            id="orbitGlow",
                            cx="50%", cy="50%", r="50%",
                        ),
                    ),
                    rx.el.circle(
                        cx="50%",
                        cy="50%",
                        r="40%",
                        stroke_width="2.5",
                        fill="url(#orbitGlow)",
                    ),
                    rx.el.circle(
                        cx="50%",
                        cy="50%",
                        r="15%",
                        fill="#36E2F4",
                        filter="drop-shadow(0 0 10px #36E2F4)",
                    ),
                    rx.el.circle(
                        cx="50%",
                        cy="50%",
                        r="5%",
                        fill="#E8F1FF",
                        class_name="blur-xs",
                    ),
                    xmlns="http://www.w3.org/2000/svg",
                    viewBox="0 0 200 200",
                    fill="none",
                    width=200,
                    height=200,
                ),
                class_name="relative flex items-center justify-center",
            ),
            rx.box(
                rx.text(
                    "OrbitLab",
                    class_name="text-[#E8F1FF] font-semibold tracking-widest text-2xl mt-8 fade-title opacity-0",
                ),
                rx.text(
                    "Initializing Control Plane...",
                    class_name="text-[#36E2F4] text-sm mt-2 fade-subtitle opacity-0",
                ),
                class_name="flex flex-col items-center justify-center",
            ),
            class_name=(
                "relative flex flex-col items-center justify-center min-h-screen w-full "
                "bg-[#0E1015] overflow-hidden select-none"
            ),
        )
