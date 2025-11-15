import reflex as rx


class UploadBox:
    """OrbitLab-themed upload drop zone with hover effects and accent transitions."""

    def __new__(cls, text: str = "", *, upload_id: str, **props: dict) -> rx.Component:
        class_name = props.pop("class_name", "")
        multiple = props.pop("multiple", True)
        if not text:
            text = "Click to upload, or drag-and-drop files."
        return rx.upload.root(
            rx.el.div(
                rx.el.p(
                    text,
                    class_name=(
                        "text-[#1E63E9] dark:text-[#36E2F4] text-sm "
                        "transition-transform duration-300 ease-in-out "
                        "group-hover:scale-110"
                    ),
                ),
                class_name=f"flex items-center justify-center p-3 text-center select-none {class_name}",
            ),
            id=upload_id,
            multiple=multiple,
            class_name=(
                # Base style & layout
                "group relative flex items-center justify-center "
                "w-fit h-fit rounded-xl border-2 border-dashed "
                "border-[#1E63E9]/40 dark:border-[#36E2F4]/30 "
                "cursor-pointer transition-all duration-300 ease-in-out "
                # Background gradient chrome
                "bg-gradient-to-b from-gray-50/90 to-gray-100/80 "
                "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                # Subtle polish + hover glow
                "shadow-sm hover:shadow-lg hover:ring-1 hover:ring-[#36E2F4]/30 "
                "hover:border-[#1E63E9]/60 dark:hover:border-[#36E2F4]/60 "
                "hover:bg-white/90 dark:hover:bg-[#14171D]/90 "
                "backdrop-blur-sm"
            ),
            **props,
        )
