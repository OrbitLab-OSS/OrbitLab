"""OrbitLab logo component module."""
import reflex as rx


class OrbitLabLogo:
    """OrbitLab logo SVG component."""

    def __new__(cls, *, size: int = 48, animated: bool = False) -> rx.Component:
        """Create a new OrbitLab logo SVG component.

        Parameters:
            size (int): The optional size of the logo in pixels, is 48 by default.

        Returns:
            rx.Component: A Reflex SVG component representing the OrbitLab logo.
        """
        return rx.el.svg(
            rx.el.defs(
                rx.el.svg.mask(
                    rx.el.rect(width="100", height="100", fill="white"),
                    rx.el.ellipse(
                        cx="50", cy="65", rx="26", ry="10",
                        fill="black",
                    ),
                    id="orbit-mask",
                    maskUnits="userSpaceOnUse",
                    width="100", height="100",
                ),
            ),
            rx.el.g(
                rx.el.circle(
                    cx="50", cy="50", r="30",
                    fill="none", stroke_width="2",
                    class_name="stroke-[#1E63E9] dark:stroke-[#36E2F4]",
                ),
                rx.el.g(
                    rx.el.ellipse(
                        cx="50", cy="50", rx="38", ry="20",
                        mask="url(#orbit-mask)",
                        class_name="stroke-[#1E63E9] dark:stroke-[#36E2F4]",
                        fill="none", stroke_width="2",
                    ),
                    transform="rotate(140 50 50)",
                ),
                rx.el.circle(
                    cx="50", cy="50", r="40",
                    stroke_width="2.5",
                    class_name="bg-radial from-[#36E2F4]/80 to-[#0E1015] dark:from-[#1E63E9]/80",
                ),
                rx.cond(
                    animated,
                    rx.el.circle(
                        cx="50", cy="50", r="15",
                        data_active=animated,
                        class_name=(
                            "fill-[#1E63E9] dark:fill-[#36E2F4] drop-shadow-[0_0_10px] drop-shadow-[#1E63E9] "
                            "dark:drop-shadow-[#36E2F4] data-[active=true]:animate-[pulse_2.8s_ease-in-out_infinite]"
                        ),
                    ),
                ),
                rx.el.circle(
                    cx="50", cy="50", r="15",
                    class_name=(
                        "fill-[#1E63E9] dark:fill-[#36E2F4] drop-shadow-[0_0_10px] drop-shadow-[#1E63E9] "
                        "dark:drop-shadow-[#36E2F4]"
                    ),
                ),
                rx.el.circle(
                    cx="50", cy="50", r="5",
                    fill="#E8F1FF",
                    data_active=animated,
                    class_name="blur-xs data-[active=true]:animate-[pulse_2.8s_ease-in-out_infinite]",
                ),
                rx.el.circle(
                    rx.cond(
                        animated,
                        rx.el.svg.animate_transform(
                            attribute_name="transform",
                            type="rotate",
                            from_="0 50 50",
                            to="360 50 50",
                            dur="2s",
                            repeat_count="indefinite",
                        ),
                    ),
                    cx="24", cy="35", r="6",
                    class_name="fill-[#1E63E9] dark:fill-[#36E2F4]",
                ),
                transform=f"scale({size / 100})",
            ),
            xmlns="http://www.w3.org/2000/svg",
            viewBox="0 0 100 100",
            fill="none",
            width=size,
            height=size,
            preserveAspectRatio="xMidYMid meet",
        )
