"""OrbitLab Networks Dashboard Dialogs."""

import contextlib
import ipaddress
from typing import Final

import reflex as rx

from orbitlab.clients.proxmox import ProxmoxNetworks
from orbitlab.data_types import FrontendEvents, SectorState
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.ipam import IpamManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.web import components
from orbitlab.web.states.manifests import ManifestsState
from orbitlab.web.states.utilities import EventGroup

from .models import CreateSectorForm, SectorSpec
from .states import CreateSectorDialogState, DeleteSectorDialogState


class CreateSectorDialog(EventGroup):
    """Dialog component for creating Sectors (virtual networks) with subnets and IPAM configuration."""

    @staticmethod
    @rx.event
    async def preload(state: CreateSectorDialogState) -> None:
        """Preload the dialog with initial form data including the next available network tag."""
        manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        state.form_data = {"tag": manifest.get_next_available_tag()}

    @staticmethod
    @rx.event
    async def set_sector_cidr(state: CreateSectorDialogState, cidr_block: str) -> None:
        """Set and validate the CIDR block for the network."""
        if cidr_block:
            with contextlib.suppress(ipaddress.AddressValueError, ValueError):
                ipaddress.IPv4Network(cidr_block)
                state.cidr_block = cidr_block
        else:
            state.cidr_block = ""

    @staticmethod
    @rx.event
    async def set_subnet_count(state: CreateSectorDialogState, subnet_count: str) -> None:
        """Set the number of subnets to create for the network."""
        state.subnet_count = int(subnet_count)

    @staticmethod
    @rx.event
    async def validate_sector(state: CreateSectorDialogState, form: dict) -> FrontendEvents:
        """Validate network configuration and proceed to next step."""
        state.form_data.update(form)
        return components.ProgressPanels.next(CreateSectorDialog.progress_id)

    @staticmethod
    @rx.event
    async def submit(state: CreateSectorDialogState, form: dict) -> FrontendEvents:
        """Create a new sector (virtual network) with configured subnets and save to cluster manifest."""
        state.form_data.update({
            "subnets": [
                {"name": form[f"subnet-{index}"] or f"subnet-{index}", "cidr_block": spec.cidr_block}
                for index, spec in enumerate(state.sector_specs)
            ],
        })
        form_data = CreateSectorForm.model_validate(state.form_data)
        sector = form_data.create_sector_manifest()
        state.reset()
        return [
            components.Dialog.close(CreateSectorDialog.dialog_id),
            ManifestsState.cache_clear("sectors"),
            rx.toast.info(f"Creating '{sector.metadata.alias}' network sector..."),
            CreateSectorDialog.start_create_sector(sector),
        ]

    @staticmethod
    @rx.event(background=True)
    async def start_create_sector(_: rx.State, sector: SectorManifest) -> FrontendEvents:
        """Create the sector in Proxmox and update its state to available."""
        networks = ProxmoxNetworks()
        await rx.run_in_thread(func=lambda: networks.create_sector(sector=sector))
        await rx.run_in_thread(func=lambda: networks.create_sector_gateway(sector=sector))
        await rx.run_in_thread(func=lambda: networks.create_sector_dns(sector=sector))
        sector.metadata.state = SectorState.AVAILABLE
        sector.save()
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        cluster_manifest.add_sector(tag=sector.metadata.tag, ref=sector.to_ref())
        return [
            ManifestsState.cache_clear("sectors"),
            rx.toast.success(f"Sector '{sector.metadata.alias}' Successfully created!"),
        ]

    @staticmethod
    @rx.event
    async def close(state: CreateSectorDialogState) -> FrontendEvents:
        """Reset the create network dialog state to its initial values."""
        state.reset()
        return components.Dialog.close(CreateSectorDialog.dialog_id)

    dialog_id: Final = "create-virtual-network-dialog"
    progress_id: Final = "create-virtual-network-progress"

    @classmethod
    def network_spec(cls, net: SectorSpec) -> rx.Component:
        """Create a data list item component displaying network specification details."""
        return components.DataList.Item(
            components.DataList.Label(net.cidr_block),
            components.DataList.Value(
                rx.el.div(
                    rx.text("Available IPs: ", rx.el.span(net.available_ips)),
                    rx.text("Available Range: ", rx.el.span(net.available_range)),
                    class_name="w-full flex-col space-y-2",
                ),
            ),
        )

    @classmethod
    def subnet_name_field(cls, sector: SectorSpec, index: int) -> rx.Component:
        """Create a field for entering subnet name."""
        return components.FieldSet.Field(
            f"Name ({sector.cidr_block}): ",
            components.Input(
                placeholder=f"subnet-{index}",
                name=f"subnet-{index}",
            ),
        )

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
            "Create Sector (Virtual Network)",
            components.ProgressPanels(
                components.ProgressPanels.Step(
                    "Sector Configuration",
                    components.Callout(
                        (
                            "OrbitLab will automatically create an IPAM for this sector and use it to assign available "
                            "IP(s) when creating compute instances in each network subnet."
                        ),
                        dismiss=True,
                    ),
                    components.FieldSet(
                        "Network",
                        components.FieldSet.Field(
                            "Sector Name: ",
                            components.Input(
                                placeholder="My Network",
                                pattern=r"^(?^i:[\(\)-_.\w\d\s]{0,256})$",
                                name="name",
                                required=True,
                                error="Network names must 1-32 alphanumeric characters",
                            ),
                        ),
                        components.FieldSet.Field(
                            "CIDR Block: ",
                            components.Input(
                                placeholder="192.168.0.0/16",
                                pattern=r"^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){2}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.0\/(8|9|1[0-9]|2[0-4])$",
                                on_change=cls.set_sector_cidr.debounce(500),
                                name="cidr_block",
                                required=True,
                            ),
                        ),
                        components.FieldSet.Field(
                            "Number of Subnets: ",
                            components.Select(
                                rx.Var.create(["2", "4", "6", "8", "10", "12"]).to(list[str]),
                                default_value="2",
                                on_change=cls.set_subnet_count,
                                name="subnet_count",
                                required=True,
                            ),
                        ),
                    ),
                    components.DataList(
                        rx.foreach(CreateSectorDialogState.sector_specs, lambda net: cls.network_spec(net)),
                    ),
                    validate=cls.validate_sector,
                ),
                components.ProgressPanels.Step(
                    "Subnet Configuration",
                    components.Callout(
                        "Subnet names are optional and will be given default names if not provided.",
                        dismiss=True,
                    ),
                    components.FieldSet(
                        "Subnets",
                        rx.foreach(
                            CreateSectorDialogState.sector_specs,
                            lambda net, index: cls.subnet_name_field(net, index),
                        ),
                    ),
                    validate=cls.submit,
                ),
                cancel_button=components.Buttons.Secondary(
                    "Cancel",
                    on_click=cls.close,
                ),
                progress_id=cls.progress_id,
            ),
            dialog_id=cls.dialog_id,
            on_open=cls.preload,
            class_name="max-w-[50vw] w-[50vw] max-h-[75vh] h-[75vh]",
        )


class DeleteSectorDialog(EventGroup):
    """Dialog component for deleting Sectors (virtual networks) with validation and cleanup."""

    @staticmethod
    @rx.event
    async def check_can_delete(state: DeleteSectorDialogState, sector_id: str) -> FrontendEvents:
        """Check if a sector can be deleted by verifying no VMs are attached to it."""
        state.sector_id = sector_id
        response = ProxmoxNetworks().list_attached(sector_id=sector_id)
        state.attached_vms = response.attached
        return components.Dialog.open(DeleteSectorDialog.dialog_id)

    @staticmethod
    @rx.event
    async def close(state: DeleteSectorDialogState) -> FrontendEvents:
        """Close the delete sector dialog and reset its state."""
        state.reset()
        return components.Dialog.close(DeleteSectorDialog.dialog_id)

    @staticmethod
    @rx.event
    async def set_confirmation(state: DeleteSectorDialogState, value: str) -> None:
        """Set the confirmation input value for sector deletion validation."""
        state.confirmation = value

    @staticmethod
    @rx.event
    async def submit(state: DeleteSectorDialogState) -> FrontendEvents:
        """Submit the sector deletion request and initiate the deletion process."""
        sector = SectorManifest.load(name=state.sector_id)
        sector.metadata.state = SectorState.DELETING
        sector.save()
        state.reset()
        return [
            components.Dialog.close(DeleteSectorDialog.dialog_id),
            ManifestsState.cache_clear("sectors"),
            rx.toast.info(f"Deleting '{sector.metadata.alias}' network sector..."),
            DeleteSectorDialog.start_sector_delete(sector),
        ]

    @staticmethod
    @rx.event(background=True)
    async def start_sector_delete(_: rx.State, sector: SectorManifest) -> FrontendEvents:
        """Delete a sector and clean up associated resources including IPAM, secrets, and cluster references."""
        await rx.run_in_thread(lambda: ProxmoxNetworks().delete_sector(sector=sector))
        IpamManifest.load(name=sector.spec.ipam.name).delete()
        ClusterManifest.load(name=next(iter(ClusterManifest.get_existing()))).remove_sector(tag=sector.metadata.tag)
        sector.delete()
        return [
            rx.toast.success(f"Sector '{sector.metadata.alias}' Successfully deleted!"),
            ManifestsState.cache_clear("sectors"),
        ]

    dialog_id: Final = "delete-sector-dialog"

    @classmethod
    def __has_attached__(cls) -> rx.Component:
        """Display component showing attached VMs that prevent sector deletion."""
        header_class = (
            "px-6 py-3 text-left text-xs font-semibold tracking-wider uppercase text-gray-600 dark:text-[#AEB9CC]"
        )
        return rx.fragment(
            rx.el.div(
                rx.el.p(
                    "There are still compute instances attached to Sector ",
                    rx.el.span(DeleteSectorDialogState.sector_id, class_name="font-bold"),
                    rx.el.span(". You must terminate them before deleting this Sector."),
                ),
                class_name="w-full my-5",
            ),
            rx.el.div(
                rx.el.table(
                    rx.el.thead(
                        rx.el.tr(
                            rx.el.th("ID", class_name=header_class),
                            rx.el.th("Name", class_name=header_class),
                            rx.el.th("IP", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(
                            DeleteSectorDialogState.attached_vms,
                            lambda vm: rx.el.tr(
                                rx.el.td(
                                    vm.vmid,  # Sector ID
                                    class_name=(
                                        "px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 "
                                        "dark:text-gray-200"
                                    ),
                                ),
                                rx.el.td(
                                    vm.name,  # Sector Name
                                    class_name=(
                                        "px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 "
                                        "dark:text-gray-200"
                                    ),
                                ),
                                rx.el.td(
                                    vm.ip,  # Sector Name
                                    class_name=(
                                        "px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 "
                                        "dark:text-gray-200"
                                    ),
                                ),
                                class_name=(
                                    "transition-colors duration-200 "
                                    "hover:bg-gray-100/60 dark:hover:bg-white/[0.06] "
                                    "hover:text-gray-900 dark:hover:text-[#E8F1FF]"
                                ),
                            ),
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
            rx.el.div(
                rx.el.div(
                    components.Buttons.Secondary("Close", on_click=cls.close),
                    class_name="w-full flex justify-end",
                ),
                class_name="w-full flex-col grow place-content-end",
            ),
        )

    @classmethod
    def __confirm_delete__(cls) -> rx.Component:
        """Display component for confirming sector deletion with name validation."""
        return rx.fragment(
            rx.el.div(
                rx.el.p(
                    "To confirm deletion of Sector ",
                    rx.el.span(DeleteSectorDialogState.sector_id, class_name="font-bold"),
                    rx.el.span(", type the name of the sector into the input below."),
                ),
                class_name="w-full my-5",
            ),
            rx.el.div(
                components.Input(
                    placeholder=DeleteSectorDialogState.sector_id,
                    on_change=cls.set_confirmation,
                ),
                class_name="w-full",
            ),
            rx.el.div(
                rx.el.div(
                    components.Buttons.Primary(
                        "Delete",
                        disabled=DeleteSectorDialogState.delete_disabled,
                        on_click=cls.submit,
                    ),
                    components.Buttons.Secondary("Close", on_click=cls.close),
                    class_name="w-full flex justify-end space-x-4",
                ),
                class_name="w-full flex-col grow place-content-end",
            ),
        )

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return components.Dialog(
            "Delete Sector",
            rx.cond(
                DeleteSectorDialogState.has_attached_compute,
                cls.__has_attached__(),
                cls.__confirm_delete__(),
            ),
            dialog_id=cls.dialog_id,
        )
