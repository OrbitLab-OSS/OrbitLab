# segmented_root_class = (
#     "inline-flex gap-1 p-1 rounded-xl "
#     "border border-gray-200 dark:border-white/[0.08] "
#     "bg-gradient-to-b from-white/90 to-gray-100/70 "
#     "dark:from-[#0E1015]/80 dark:to-[#181B22]/80 "
#     "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.10)] "
#     "dark:shadow-[inset_0_0_0.5px_rgba(255,255,255,0.08)] "
#     # kill Reflex/Radix moving selected background
#     "[&_.rt-SegmentedControlIndicator]:!hidden "
#     "[&_.rt-SegmentedControlIndicator]:!bg-transparent "
#     "[&_.rt-SegmentedControlIndicator]:!shadow-none "
#     "[&_.rt-SegmentedControlIndicator]:!opacity-0 "
# )

# segmented_item_class = (
#     "px-4 py-2 rounded-lg text-sm font-medium "
#     "transition-all duration-300 ease-in-out "
#     "text-gray-500 dark:text-gray-400 "
#     "hover:ring-1 hover:ring-[#36E2F4]/30 "
#     "data-[state=on]:text-gray-900 "
#     "dark:data-[state=on]:text-[#E8F1FF] "
#     "data-[state=on]:border "
#     "data-[state=on]:border-gray-200 "
#     "dark:data-[state=on]:border-white/[0.08] "
#     "data-[state=on]:shadow-[inset_0_0_0.5px_rgba(255,255,255,0.10)] "
#     "dark:data-[state=on]:shadow-[inset_0_0_0.5px_rgba(255,255,255,0.08)] "
#     "data-[state=on]:ring-1 "
#     "data-[state=on]:ring-[#36E2F4]/20 "
#     "[&_*]:!bg-transparent "
#     "hover:[&_*]:!bg-transparent"
# )
# rx.segmented_control.root(
#     rx.segmented_control.item(
#         "System",
#         value="system",
#         class_name=segmented_item_class,
#     ),
#     rx.segmented_control.item(
#         "Dark",
#         value="dark",
#         class_name=segmented_item_class,
#     ),
#     rx.segmented_control.item(
#         "Light",
#         value="light",
#         class_name=segmented_item_class,
#     ),
#     default_value=SelectionDefaults.color_mode,
#     on_change=[cls.set_color_mode, rx.style.set_color_mode],
#     class_name=segmented_root_class,
# )
