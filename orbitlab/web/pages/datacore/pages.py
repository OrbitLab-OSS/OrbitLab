"""Dashboard module for displaying and managing Proxmox nodes."""

import reflex as rx

from orbitlab.data_types import FrontendEvents, ETCDStatus
from orbitlab.web import components
from orbitlab.web.defaults import ClusterDefaults
from orbitlab.web.utilities import get_worker
from orbitlab.web.layout import orbitlab_page

from .dialogs import CreateDataCoreDialog, DeleteDataCoreDialog, DeleteETCDDialog
from .states import DataCoreServiceState
from .tables import DataCoreClustersTable


@rx.event
async def create_etcd_cluster(_: rx.State) -> FrontendEvents:
    worker = get_worker()
    error = await worker.create_workflow(
        name="datacore.etcd.create",
        version="v1",
        payload={},
    )
    if error:
        return rx.toast.error(error)
    return  rx.toast.info("Creating ETCD cluster...")


@rx.page("/datacore")
@orbitlab_page
def datacore_dashboard() -> rx.Component:
    """DataCore Dashboard Page."""
    return rx.cond(
        ClusterDefaults.etcd_enabled,
        rx.el.div(
            components.PageHeader(
                "DataCores",
                components.Buttons.Primary(
                    "Create DataCore",
                    icon="plus",
                    on_click=CreateDataCoreDialog.open,
                    disabled=DataCoreServiceState.etcd_mutation_in_progress,
                ),
            ),
            components.Card(
                rx.el.div(
                    rx.text("ETCD Cluster"),
                    rx.match(
                        DataCoreServiceState.etcd_cluster_status,
                        (ETCDStatus.AVAILABLE, components.Badge(DataCoreServiceState.etcd_cluster_status.to(str).capitalize(), color_scheme="green")),
                        (ETCDStatus.DEGRADED, components.Badge(DataCoreServiceState.etcd_cluster_status.to(str).capitalize(), color_scheme="orange")),
                        (ETCDStatus.DELETING, components.Badge(DataCoreServiceState.etcd_cluster_status.to(str).capitalize(), color_scheme="red")),
                        components.Badge(DataCoreServiceState.etcd_cluster_status.to(str).capitalize(), color_scheme="blue"),
                    ),
                    components.Buttons.Primary("Delete ETCD", on_click=DeleteETCDDialog.confirm, disabled=DataCoreServiceState.etcd_mutation_in_progress),
                    class_name="w-full flex items-center justify-between px-3 py-2"
                ),
                class_name="mt-4"
            ),
            DataCoreClustersTable(),
            CreateDataCoreDialog(),
            DeleteDataCoreDialog(),
            DeleteETCDDialog(),
            class_name="w-full h-full",
        ),
        rx.el.div(
            components.Callout(
                (
                    "To create DataCores, you need to opt-in to ETCD. An ETCD cluster is required for DataCore "
                    "cluster management (Patroni). This isn't created by default to minimize impact to Proxmox "
                    "and the available resources of a given node/cluster.\n\nClick 'Create ETCD' to establish "
                    "an ETCD cluster and enable creating DataCores."
                ),
            ),
            rx.el.div(
                components.Buttons.Primary("Create ETCD", on_click=create_etcd_cluster, disabled=DataCoreServiceState.etcd_mutation_in_progress),
                class_name="w-full flex items-center justify-center mt-8",
            )
        ),
    )
