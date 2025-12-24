"""OrbitLab LXC Tables."""

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.manifest.appliances import BaseApplianceManifest, CustomApplianceManifest, Step
from orbitlab.services.discovery import DiscoveryService
from orbitlab.web import components
from orbitlab.web.states.manifests import ManifestsState
from orbitlab.web.states.utilities import EventGroup

from .dialogs import CreateApplianceDialog


class BaseApplianceTable(EventGroup):
    """A table component for displaying base appliance manifests.

    This class provides functionality to display base appliances in a table format
    with refresh capabilities and discovery management features.
    """

    @staticmethod
    @rx.event
    async def run_appliance_discovery(_: rx.State) -> FrontendEvents:
        """Run appliance discovery and refresh the base appliances list."""
        await rx.run_in_thread(DiscoveryService().discover_appliances)
        return ManifestsState.cache_clear("base_appliances")

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
                components.Menu(
                    components.Buttons.Icon("ellipsis-vertical"),
                    components.Menu.Item(
                        "Create Custom Appliance",
                        on_click=CreateApplianceDialog.create_appliance_from_base(appliance.name),
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
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(ManifestsState.base_appliances, lambda app: cls.__table_row__(app)),
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
                        components.Buttons.Icon("refresh-ccw", on_click=ManifestsState.cache_clear("base_appliances")),
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


class CustomApplianceTable:
    """A table component for displaying custom appliance manifests.

    This class provides functionality to display custom appliances in a table format
    with details about their base appliances, certificate authorities, workflow steps,
    and creation dates.
    """

    @classmethod
    def __step_info__(cls, step: Step, index: int) -> rx.Component:
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
                components.Menu(
                    components.Buttons.Icon("ellipsis-vertical"),
                    components.Menu.Item(
                        "Rerun Workflow",
                        on_click=rx.console_log("NOT IMPLEMENTED")
                        # on_click=RunCustomApplianceWorkflowDialog.run(appliance),
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
                            rx.el.th("Workflow Steps", class_name=header_class),
                            rx.el.th("Date Created", class_name=header_class),
                            rx.el.th("", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(ManifestsState.custom_appliances, lambda app: cls.__table_row__(app)),
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
                    rx.el.h3("Custom Appliances"),
                    rx.el.div(
                        components.Buttons.Icon(
                            "refresh-ccw",
                            on_click=ManifestsState.cache_clear("custom_appliances"),
                        ),
                        class_name="flex space-x-4",
                    ),
                    class_name="w-full flex justify-between",
                ),
            ),
            class_name="w-full mt-6",
        )
