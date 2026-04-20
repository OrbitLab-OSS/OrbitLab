"""Dashboard module for displaying and managing Proxmox nodes."""

import reflex as rx

from orbitlab.data_types import FrontendEvents, ETCDStatus
from orbitlab.web import tailwind
from orbitlab.web.components.dialogs import ConfirmUpdateInfrastructureDialog
from orbitlab.web.global_state import ETCDState, InfrastructureManagementState
from orbitlab.web.utilities import create_workflow
from orbitlab.web.layout import orbitlab_page

from .dialogs import CreateDataCoreDialog, DeleteDataCoreDialog, DeleteETCDDialog, UpgradeETCDDialog
from .tables import DataCoreClustersTable


@rx.event
async def create_etcd_cluster(_: rx.State) -> FrontendEvents:
    if error := await create_workflow(name="datacore.etcd.create", version="v1", payload={}):
        return rx.toast.error(error)
    return rx.toast.info("Creating ETCD cluster...")


@rx.event
async def update_cluster(state: InfrastructureManagementState) -> FrontendEvents:
    if await state.infrastructure_update_available:
        return ConfirmUpdateInfrastructureDialog.open
    return tailwind.Dialog.open(UpgradeETCDDialog.dialog_id)


@rx.page("/datacore")
@orbitlab_page
def datacore_dashboard() -> rx.Component:
    """DataCore Dashboard Page."""
    return rx.cond(
        ETCDState.status != ETCDStatus.ABSENT,
        rx.el.div(
            tailwind.PageHeader(
                "DataCores",
                tailwind.Buttons.Primary(
                    "Create DataCore",
                    icon="plus",
                    on_click=CreateDataCoreDialog.open,
                    disabled=ETCDState.etcd_mutation_in_progress,
                ),
            ),
            tailwind.Card(
                rx.el.div(
                    rx.text("ETCD Cluster"),
                    rx.match(
                        ETCDState.status,
                        (ETCDStatus.AVAILABLE, tailwind.Badge(ETCDState.status.to(str).capitalize(), color_scheme="green")),
                        (ETCDStatus.DEGRADED, tailwind.Badge(ETCDState.status.to(str).capitalize(), color_scheme="orange")),
                        (ETCDStatus.DELETING, tailwind.Badge(ETCDState.status.to(str).capitalize(), color_scheme="red")),
                        tailwind.Badge(ETCDState.status.to(str).capitalize(), color_scheme="blue"),
                    ),
                    tailwind.Badge(f"v{ETCDState.version}", color_scheme="blue"),
                    tailwind.Menu(
                        tailwind.WithStatus(
                            tailwind.Buttons.Primary("Manage ETCD", icon="chevron-down"),
                            color="red",
                            animate=True,
                            disabled=ETCDState.etcd_is_latest,
                        ),
                        tailwind.Menu.Item(
                            rx.cond(
                                ETCDState.etcd_is_latest,
                                "No Upgrade Available",
                                f"Upgrade to v{InfrastructureManagementState.latest_version}",
                            ),
                            disabled=ETCDState.etcd_is_latest,
                            on_click=update_cluster
                        ),
                        tailwind.Menu.Separator(),
                        tailwind.Menu.Item("Delete Cluster", danger=True, on_click=DeleteETCDDialog.confirm),
                    ),
                    class_name="w-full flex items-center justify-between px-3 py-2"
                ),
                class_name="mt-4"
            ),
            DataCoreClustersTable(),
            CreateDataCoreDialog(),
            DeleteDataCoreDialog(),
            UpgradeETCDDialog(),
            DeleteETCDDialog(),
            ConfirmUpdateInfrastructureDialog(),
            class_name="w-full h-full",
        ),
        rx.el.div(
            tailwind.Callout(
                (
                    "To create DataCores, you need to opt-in to ETCD. An ETCD cluster is required for DataCore "
                    "cluster management (Patroni). This isn't created by default to minimize impact to Proxmox "
                    "and the available resources of a given node/cluster.\n\nClick 'Create ETCD' to establish "
                    "an ETCD cluster and enable creating DataCores."
                ),
            ),
            rx.el.div(
                # components.Buttons.Primary("Create ETCD", on_click=create_etcd_cluster, disabled=OrbitLabState.etcd_mutation_in_progress),
                tailwind.Buttons.Primary("Create ETCD", on_click=create_etcd_cluster),
                class_name="w-full flex items-center justify-center mt-8",
            )
        ),
    )
