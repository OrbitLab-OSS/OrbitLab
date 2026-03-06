"""DockFS Tables."""

import reflex as rx

from orbitlab.data_types import DockFSState, FrontendEvents
from orbitlab.manifest.datacore import DataCoreManifest, Ref
from orbitlab.manifest.secrets import SecretManifest
from orbitlab.web import components
from orbitlab.web.utilities import EventGroup

from .dialogs import DeleteDataCoreDialog
from .states import DataCoreServiceState


class DataCoreClustersTable(EventGroup):
    """Table component for displaying and managing DataCore clusters in OrbitLab."""

    @staticmethod
    @rx.event
    def copy_password_to_clipboard(_: rx.State, ref: Ref) -> FrontendEvents:
        """Copy a secret password to the clipboard."""
        return [
            rx.set_clipboard(SecretManifest.load(name=ref.name).get_current_value()),
            rx.toast.success("Copied to clipboard"),
        ]

    @classmethod
    def __table_row__(cls, manifest: DataCoreManifest) -> rx.Component:
        """Create and return the table row component."""
        state = DataCoreServiceState.state_map.get(manifest.name).to(str)
        return rx.el.tr(
            rx.el.td(
                rx.el.div(
                    rx.text(manifest.metadata.name),
                    rx.text(manifest.name, class_name="text-sm text-gray-500"),
                    class_name="flex-col space-y-1 items-center",
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.text(manifest.spec.replicas),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.text(manifest.spec.application_database),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.text(manifest.spec.application_user),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.match(
                    state,
                    (DockFSState.AVAILABLE, components.Badge(state.capitalize(), color_scheme="green")),
                    (DockFSState.DEGRADED, components.Badge(state.capitalize(), color_scheme="orange")),
                    (DockFSState.DELETING, components.Badge(state.capitalize(), color_scheme="red")),
                    components.Badge(state.capitalize(), color_scheme="blue"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.text(f"{manifest.spec.capacity_gb}GB"),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.text(manifest.spec.cores),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.text(f"{manifest.spec.memory_gb}G"),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                components.Menu(
                    components.Buttons.Icon("ellipsis-vertical"),
                    components.Menu.Item(
                        "Copy App User Password to Clipboard",
                        on_click=cls.copy_password_to_clipboard(manifest.spec.application_password),
                    ),
                    components.Menu.Item(
                        "Copy Superuser Password to Clipboard",
                        on_click=cls.copy_password_to_clipboard(manifest.spec.superuser_password),
                    ),
                    components.Menu.Separator(),
                    components.Menu.Item(
                        "Expand Storage",
                        disabled=True,
                        # TODO: Allow for increasing NFS data disk size
                    ),
                    components.Menu.Separator(),
                    components.Menu.Item(
                        "Delete",
                        on_click=DeleteDataCoreDialog.confirm(manifest.name),
                        danger=True,
                    ),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            class_name=(
                "transition-colors duration-200 "
                "hover:bg-gray-100/60 dark:hover:bg-white/[0.06] "
                "hover:text-gray-900 dark:hover:text-[#E8F1FF]"
            ),
        )

    def __new__(cls) -> rx.Component:
        """Create and return the appliance templates table component."""
        header_class = (
            "px-6 py-3 text-left text-xs font-semibold tracking-wider uppercase text-gray-600 dark:text-[#AEB9CC]"
        )
        return components.Card(
            rx.el.div(
                rx.el.table(
                    rx.el.thead(
                        rx.el.tr(
                            rx.el.th("DataCore", class_name=header_class),
                            rx.el.th("Replicas", class_name=header_class),
                            rx.el.th("App DB", class_name=header_class),
                            rx.el.th("App User", class_name=header_class),
                            rx.el.th("Status", class_name=header_class),
                            rx.el.th("Capacity", class_name=header_class),
                            rx.el.th("Cores", class_name=header_class),
                            rx.el.th("Memory", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(
                            DataCoreServiceState.clusters,
                            lambda manifest: cls.__table_row__(manifest=manifest),
                        ),
                        class_name=(
                            "divide-y divide-gray-200 dark:divide-white/[0.08] bg-white/70 dark:bg-[#0E1015]/60 "
                            "backdrop-blur-sm"
                        ),
                    ),
                    class_name=(
                        "min-w-full text-sm text-gray-800 dark:text-gray-200 "
                        "divide-y divide-gray-200 dark:divide-white/[0.08]"
                    ),
                ),
                class_name=(
                    "border border-gray-200 dark:border-white/[0.08] "
                    "rounded-b-xl overflow-x-auto shadow-md "
                    "bg-gradient-to-b from-white/90 to-gray-50/70 "
                    "dark:from-[#0E1015]/80 dark:to-[#12141A]/80 "
                    "hover:ring-1 hover:ring-[#36E2F4]/40 "
                    "transition-all duration-200"
                ),
            ),
            header=components.Card.Header(
                rx.el.div(
                    rx.el.div(),
                    rx.el.div(
                        components.Buttons.Icon("refresh-ccw", on_click=DataCoreServiceState.cache_clear("clusters")),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between",
                ),
            ),
            class_name="w-full mt-6",
        )
