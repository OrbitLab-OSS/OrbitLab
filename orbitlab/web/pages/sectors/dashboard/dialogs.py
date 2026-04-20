"""OrbitLab Networks Dashboard Dialogs."""

from ipaddress import IPv4Network
from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.proxmox import ProxmoxNetworks
from orbitlab.redis.clients import SectorClient, BackplaneClient
from orbitlab.redis.models import SectorConfiguration
from orbitlab.web import tailwind
from orbitlab.web.global_state import SelectionDefaults
from orbitlab.web.utilities import EventGroup, create_workflow

from .states import DeleteSectorDialogState


class CreateSectorDialog(EventGroup):
    """Dialog component for creating Sectors (virtual networks) with subnets and IPAM configuration."""

    @staticmethod
    @rx.event
    async def submit(state: rx.State, form: dict) -> FrontendEvents:
        """Create a new sector (virtual network)."""
        tag = await BackplaneClient().get_next_vlan_tag()
        if not tag:
            return rx.toast.error("No available VLAN tag to assign to new sector.")
        
        backplane_address = await BackplaneClient().get_next_available_ip()
        
        config = SectorConfiguration(
            id=f"olvn{tag}",
            cidr_block=IPv4Network(form["cidr_block"]),
            alias=form["alias"],
            tag=tag,
            backplane_address=backplane_address,
            storage=await state.get_var_value(SelectionDefaults.default_rootdir_storage),
        )
        await SectorClient().set(config=config)
        if error := await create_workflow(name="sector.create", version="v1", payload={"id": config.id}):
            return rx.toast.error(error)
        return [
            tailwind.Dialog.close(CreateSectorDialog.dialog_id),
            rx.toast.info(f"Creating '{config.id}' network sector..."),
        ]

    dialog_id: Final = "create-virtual-network-dialog"
    form_id: Final = "create-virtual-network-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return tailwind.Dialog(
            "Create Sector (Virtual Network)",
            rx.el.div(
                rx.el.form(id=cls.form_id, on_submit=cls.submit),
                tailwind.FieldSet(
                    "Network",
                    tailwind.FieldSet.Field(
                        "Sector Name: ",
                        tailwind.Input(
                            placeholder="My Network",
                            pattern=r"^(?^i:[\(\)-_.\w\d\s]{0,256})$",
                            form=cls.form_id,
                            name="alias",
                            required=True,
                            error="Network names must 1-32 alphanumeric characters",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "CIDR Block: ",
                        tailwind.Input(
                            placeholder="192.168.0.0/16",
                            pattern=r"^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){2}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.0\/(8|9|1[0-9]|2[0-4])$",
                            form=cls.form_id,
                            name="cidr_block",
                            required=True,
                            error="Must be a valid network CIDR block",
                        ),
                    ),
                ),
                rx.el.div(
                    tailwind.Buttons.Secondary("Cancel", on_click=tailwind.Dialog.close(CreateSectorDialog.dialog_id)),
                    tailwind.Buttons.Primary("Submit", form=cls.form_id),
                    class_name="w-full flex space-x-4 justify-end",
                ),
                class_name="w-full flex-col space-y-10",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[50vw] w-[50vw] max-h-[75vh] h-fit",
        )


class DeleteSectorDialog(EventGroup):
    """Dialog component for deleting Sectors (virtual networks) with validation and cleanup."""

    @staticmethod
    @rx.event
    async def check_can_delete(state: DeleteSectorDialogState, sector_id: str) -> FrontendEvents:
        """Check if a sector can be deleted by verifying no VMs are attached to it."""
        state.sector_id = sector_id
        state.attached_vms = await ProxmoxNetworks().list_attached(sector_id=sector_id)
        return tailwind.Dialog.open(DeleteSectorDialog.dialog_id)

    @staticmethod
    @rx.event
    async def close(state: DeleteSectorDialogState) -> FrontendEvents:
        """Close the delete sector dialog and reset its state."""
        state.reset()
        return tailwind.Dialog.close(DeleteSectorDialog.dialog_id)

    @staticmethod
    @rx.event
    async def set_confirmation(state: DeleteSectorDialogState, value: str) -> None:
        """Set the confirmation input value for sector deletion validation."""
        state.confirmation = value

    @staticmethod
    @rx.event
    async def submit(state: DeleteSectorDialogState) -> FrontendEvents:
        """Submit the sector deletion request and initiate the deletion process."""
        if error := await create_workflow(name="sector.delete", version="v1", payload={"id": state.sector_id}):
            return rx.toast.error(error)
        return [
            tailwind.Dialog.close(DeleteSectorDialog.dialog_id),
            rx.toast.info(f"Deleting '{state.sector_id}' network sector..."),
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
                            rx.el.th("Type", class_name=header_class),
                        ),
                        class_name="bg-white/60 dark:bg-white/[0.03] backdrop-blur-sm",
                    ),
                    rx.el.tbody(
                        rx.foreach(
                            DeleteSectorDialogState.attached_vms,
                            lambda vm: rx.el.tr(
                                rx.el.td(
                                    vm.vmid,  # VM ID
                                    class_name=(
                                        "px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-800 "
                                        "dark:text-gray-200"
                                    ),
                                ),
                                rx.el.td(
                                    vm.compute_type,  # Compute Type
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
                    tailwind.Buttons.Secondary("Close", on_click=cls.close),
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
                tailwind.Input(
                    placeholder=DeleteSectorDialogState.sector_id,
                    on_change=cls.set_confirmation,
                ),
                class_name="w-full",
            ),
            rx.el.div(
                rx.el.div(
                    tailwind.Buttons.Primary(
                        "Delete",
                        disabled=DeleteSectorDialogState.delete_disabled,
                        on_click=cls.submit,
                    ),
                    tailwind.Buttons.Secondary("Close", on_click=cls.close),
                    class_name="w-full flex justify-end space-x-4",
                ),
                class_name="w-full flex-col grow place-content-end",
            ),
        )

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return tailwind.Dialog(
            "Delete Sector",
            rx.cond(
                DeleteSectorDialogState.has_attached_compute,
                cls.__has_attached__(),
                cls.__confirm_delete__(),
            ),
            dialog_id=cls.dialog_id,
        )
