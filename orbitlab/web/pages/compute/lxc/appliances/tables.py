"""OrbitLab LXC Tables."""

from datetime import UTC, datetime

import reflex as rx

from orbitlab.clients.proxmox.appliances import ProxmoxAppliances
from orbitlab.data_types import CustomApplianceWorkflowStatus, FrontendEvents
from orbitlab.manifest.appliances import BaseApplianceManifest, CustomApplianceManifest, FileStep, ScriptStep
from orbitlab.services.discovery import DiscoveryService
from orbitlab.web import components
from orbitlab.web.utilities import EventGroup

from .dialogs import CustomApplianceDialog, CustomApplianceState, DeleteConfirmationDialog
from .states import AppliancesState


class BaseApplianceTable(EventGroup):
    """A table component for displaying base appliance manifests."""

    @staticmethod
    @rx.event
    async def run_appliance_discovery(_: rx.State) -> FrontendEvents:
        """Run appliance discovery and refresh the base appliances list."""
        await rx.run_in_thread(DiscoveryService().discover_appliances)
        return AppliancesState.cache_clear("base_appliances")

    @staticmethod
    @rx.event(background=True)
    async def delete(_: rx.State, name: str) -> FrontendEvents:
        """Run appliance discovery and refresh the base appliances list."""
        appliance = BaseApplianceManifest.load(name=name)
        await rx.run_in_thread(lambda: ProxmoxAppliances().delete_appliance(appliance=appliance))
        appliance.delete()
        return [
            AppliancesState.cache_clear("base_appliances"),
            rx.toast.success(f"Appliance {name} successfully deleted."),
        ]

    @staticmethod
    @rx.event(background=True)
    async def re_download_appliance(_: rx.State, name: str) -> FrontendEvents:
        """Re-download the specified appliance by name."""
        appliance = BaseApplianceManifest.load(name=name)
        await rx.run_in_thread(lambda: ProxmoxAppliances().download_appliance(appliance=appliance))
        appliance.metadata.download_date = datetime.now(UTC)
        appliance.save()
        return [
            AppliancesState.cache_clear("base_appliances"),
            rx.toast.success(f"Appliance {name} download complete!"),
        ]

    @classmethod
    def __table_row__(cls, appliance: BaseApplianceManifest) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                appliance.name,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                appliance.spec.node.ref.replace("node/", "").replace(".yaml", ""),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                appliance.spec.storage,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.el.p(appliance.metadata.description, class_name="truncate"),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.moment(appliance.metadata.download_date, from_now_during=172800, format="YYYY-MM-DD HH:mm:ss"),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                components.Menu(
                    components.Buttons.Icon("ellipsis-vertical"),
                    components.Menu.Item(
                        "Re-Download",
                        on_click=[
                            rx.toast.info(f"Re-downloading {appliance.name}..."),
                            BaseApplianceTable.re_download_appliance(appliance.name),
                        ],
                    ),
                    components.Menu.Item(
                        "Create Custom Appliance",
                        on_click=CustomApplianceDialog.start_appliance_creation(appliance.name),
                    ),
                    components.Menu.Separator(),
                    components.Menu.Item(
                        "Delete",
                        on_click=cls.delete(appliance.name),
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
                            rx.el.th("Name", class_name=header_class),
                            rx.el.th("Node", class_name=header_class),
                            rx.el.th("Storage", class_name=header_class),
                            rx.el.th("Description", class_name=header_class),
                            rx.el.th("Date Downloaded", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
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
            header=components.Card.Header(
                rx.el.div(
                    rx.el.h3("Base Appliances"),
                    rx.el.div(
                        components.Buttons.Icon("refresh-ccw", on_click=AppliancesState.cache_clear("base_appliances")),
                        components.Menu(
                            components.Buttons.Primary("Manage", icon="chevron-down"),
                            components.Menu.Item("Rerun Discovery", on_click=cls.run_appliance_discovery),
                        ),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between",
                ),
            ),
            class_name="w-full mt-6",
        )


class CustomApplianceTable(EventGroup):
    """A table component for displaying custom appliance manifests."""

    @staticmethod
    @rx.event
    async def edit_appliance(state: CustomApplianceState, name: str) -> FrontendEvents:
        """Edit a custom appliance by name and open the dialog."""
        state.edit_mode = True
        appliance = CustomApplianceManifest.load(name=name)
        return [
            CustomApplianceState.load_appliance(appliance),
            components.Dialog.open(CustomApplianceDialog.dialog_id),
        ]

    @classmethod
    def __step_info__(cls, step: ScriptStep | FileStep, index: int) -> rx.Component:
        """Create a component displaying step information with index and type badge."""
        return rx.el.div(
            rx.text(f"{index + 1}. {step.name} ", rx.el.span(components.Badge(step.type, color_scheme="blue"))),
            class_name="w-fit p-2 flex-col space-y-2",
        )

    @classmethod
    def __table_row__(cls, appliance: CustomApplianceManifest) -> rx.Component:
        """Create and return the table row component."""
        return rx.el.tr(
            rx.el.td(
                appliance.name,
                class_name="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 dark:text-gray-200",
            ),
            rx.el.td(
                appliance.spec.base_appliance,
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.foreach(
                    rx.Var.create(appliance.spec.certificate_authorities).to(list[str]),
                    lambda cert: components.Badge(cert, color_scheme="blue"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300 space-x-1",
            ),
            rx.el.td(
                rx.match(
                    appliance.metadata.status,
                    (
                        CustomApplianceWorkflowStatus.SUCCEEDED,
                        components.Badge(appliance.metadata.status.capitalize(), color_scheme="green"),
                    ),
                    (
                        CustomApplianceWorkflowStatus.FAILED,
                        components.Badge(appliance.metadata.status.capitalize(), color_scheme="red"),
                    ),
                    components.Badge(appliance.metadata.status.capitalize(), color_scheme="blue"),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                components.HoverCard(
                    rx.text(rx.Var.create(appliance.spec.steps).to(list).length(), class_name="w-full pl-10"),
                    rx.foreach(appliance.spec.steps, lambda step, index: cls.__step_info__(step, index)),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.moment(appliance.metadata.created_on, local=True, from_now_during=1209600000),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                rx.cond(
                    rx.Var.create(appliance.metadata.last_execution).is_none(),
                    rx.text("Not Ran"),
                    rx.moment(appliance.metadata.last_execution, local=True, from_now_during=1209600000),
                ),
                class_name="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300",
            ),
            rx.el.td(
                components.Menu(
                    components.Buttons.Icon("ellipsis-vertical"),
                    components.Menu.Item(
                        "Edit",
                        on_click=cls.edit_appliance(appliance.name),
                    ),
                    components.Menu.Item(
                        "Rerun Workflow",
                        on_click=CustomApplianceDialog.run_workflow(appliance.name),
                    ),
                    components.Menu.Separator(),
                    components.Menu.Item(
                        "Delete",
                        on_click=DeleteConfirmationDialog.confirm_deletion(appliance.name),
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
                            rx.el.th("Name", class_name=header_class),
                            rx.el.th("Base Appliance", class_name=header_class),
                            rx.el.th("Trusted CAs", class_name=header_class),
                            rx.el.th("Workflow Status", class_name=header_class),
                            rx.el.th("Workflow Steps", class_name=header_class),
                            rx.el.th("Date Created", class_name=header_class),
                            rx.el.th("Last Execution", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(AppliancesState.custom_appliances, lambda app: cls.__table_row__(app)),
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
            CustomApplianceDialog(),
            DeleteConfirmationDialog(),
            header=components.Card.Header(
                rx.el.div(
                    rx.el.h3("Custom Appliances"),
                    rx.el.div(
                        components.Buttons.Icon(
                            "refresh-ccw",
                            on_click=AppliancesState.cache_clear("custom_appliances"),
                        ),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between",
                ),
            ),
            class_name="w-full mt-6",
        )
