
from typing import Literal

import reflex as rx

from orbitlab.data_types import StorageContentType
from orbitlab.proxmox.compute_templates import ProxmoxComputeTemplates
from orbitlab.web.global_state import SelectOptions


class CreatePoolDialogState(rx.State):

    form_data: rx.Field[dict] = rx.field(default_factory=dict)
    
    compute_type: rx.Field[Literal["lxc", "vm"]] = rx.field(default="lxc")

    @rx.var
    def node(self) -> str:
        return self.form_data.get("node", "")

    @rx.var
    async def available_bases(self) -> dict[str, str]:
        """Get the available base image/appliance options."""
        if self.compute_type == "lxc":
            bases = await self.get_var_value(SelectOptions.custom_appliance_options)
        else:
            bases = await self.get_var_value(SelectOptions.custom_image_options)
        return await bases

    @rx.var
    def available_storage(self) -> list[str]:
        """Get the available rootfs options for the selected node."""
        if self.node:
            if self.compute_type == "lxc":
                return ProxmoxComputeTemplates().list_storages_for_node(
                    node=self.node, content_type=StorageContentType.ROOTDIR,
                )
            return ProxmoxComputeTemplates().list_storages_for_node(
                node=self.node, content_type=StorageContentType.IMAGES,
            )
        return []

    @rx.event
    async def toggle_compute_type(self) -> None:
        if self.compute_type == "lxc":
            self.compute_type = "vm"
        else:
            self.compute_type = "lxc"
