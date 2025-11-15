import reflex as rx

from orbitlab.data_types import ManifestKind
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.appliances import BaseApplianceManifest
from orbitlab.web.components import Buttons, Card, Menu, PageHeader

from .dialogs import DialogStateManager, DownloadApplianceDialog
from .dialogs.create_appliance import CreateApplianceDialog, create_appliance_from_base


def get_base_appliances() -> list[BaseApplianceManifest]:
    client = ManifestClient()
    return [
        client.load(name, kind=ManifestKind.BASE_APPLIANCE)
        for name in client.get_existing_by_kind(kind=ManifestKind.BASE_APPLIANCE)
    ]


class AppliancesState(rx.State):
    base_appliances: list[BaseApplianceManifest] = rx.field(default_factory=get_base_appliances)


@rx.event
async def refresh_base_appliances(state: AppliancesState):
    state.base_appliances = get_base_appliances()


class BaseApplianceTable:
    @classmethod
    def __table_row__(cls, appliance: BaseApplianceManifest) -> rx.Component:
        return rx.el.tr(
            rx.el.td(
                appliance.name,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                rx.cond(
                    appliance.metadata.turnkey,
                    rx.badge(
                        "TurnKey",
                        class_name=(
                            "bg-[#36E2F4]/15 text-[#36E2F4] border border-[#36E2F4]/30 "
                            "dark:bg-[#36E2F4]/20 dark:text-[#36E2F4]"
                        ),
                    ),
                    rx.badge(
                        "System",
                        class_name=(
                            "bg-[#1E63E9]/15 text-[#1E63E9] border border-[#1E63E9]/30 "
                            "dark:bg-[#1E63E9]/20 dark:text-[#1E63E9]"
                        ),
                    ),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                appliance.spec.os_type,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                appliance.spec.version,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                appliance.spec.architecture,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                appliance.spec.storage,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                appliance.metadata.section,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                Menu(
                    Buttons.Icon("ellipsis-vertical"),
                    Menu.Item("Create Custom Appliance", on_click=lambda: create_appliance_from_base(appliance.name)),
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
        return Card(
            rx.el.div(
                rx.el.table(
                    # === Table Header ===
                    rx.el.thead(
                        rx.el.tr(
                            rx.el.th("Name", class_name=header_class),
                            rx.el.th("Type", class_name=header_class),
                            rx.el.th("OS", class_name=header_class),
                            rx.el.th("Version", class_name=header_class),
                            rx.el.th("Arch", class_name=header_class),
                            rx.el.th("Storage", class_name=header_class),
                            rx.el.th("Section", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    # === Table Body ===
                    rx.el.tbody(
                        rx.foreach(AppliancesState.base_appliances, lambda app: cls.__table_row__(app)),
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
            header=Card.Header(
                rx.el.div(
                    rx.el.h3("Base Appliances"),
                    Buttons.Icon("refresh-ccw", on_click=refresh_base_appliances),
                    class_name="w-full flex justify-between",
                ),
            ),
            class_name="w-full mt-6",
        )


class Appliances:
    def __new__(cls) -> rx.Component:
        return rx.el.div(
            PageHeader(
                "LXC Appliance Management",
                Buttons.Secondary(
                    "Create Custom Appliance",
                    icon="pen",
                    on_click=DialogStateManager.toggle(CreateApplianceDialog.dialog_id),
                ),
                Buttons.Primary(
                    "Download Base Appliance",
                    icon="cloud-download",
                    on_click=DialogStateManager.toggle(DownloadApplianceDialog.dialog_id),
                ),
            ),
            BaseApplianceTable(),
            DownloadApplianceDialog(),
            CreateApplianceDialog(),
            class_name="w-full h-full flex flex-col",
        )
