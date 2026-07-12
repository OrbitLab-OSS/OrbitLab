"""OrbitLab LXC States."""

from collections.abc import Awaitable
from typing import Literal, cast

import reflex as rx

from orbitlab.data_types import ApplianceType
from orbitlab.proxmox import Proxmox
from orbitlab.proxmox.models import ApplianceInfo
from orbitlab.redis.clients import ApplianceClient
from orbitlab.redis.models import BaseAppliance
from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState, SelectionDefaults
from orbitlab.worker.workflows.models import FileConfig, WorkflowStep


class ApplianceWorkflowLogsViewDialogState(OrbitLabState):
    """State management for custom LXC appliances."""
    
    view_workflow: rx.Field[str] = rx.field(default="")
    workflow_running: rx.Field[bool] = rx.field(default=False)
    logs: rx.Field[str] = rx.field(default="")
    countdown_refresh_seconds: rx.Field[int] = rx.field(default=5)


class PullOCIApplianceDialogState(rx.State):
    node: rx.Field[str] = rx.field(default="")



class DownloadApplianceState(rx.State):
    """State management for downloading appliances from Proxmox."""

    appliance_view: rx.Field[ApplianceType] = rx.field(default=ApplianceType.SYSTEM)
    query_string: rx.Field[str] = rx.field(default="")
    download_configs: rx.Field[dict[str, str]] = rx.field(default_factory=dict)

    _turnkey_appliances: rx.Field[list[ApplianceInfo]] = rx.field(default_factory=list)
    _system_appliances: rx.Field[list[ApplianceInfo]] = rx.field(default_factory=list)

    @rx.var
    def turnkey_appliances(self) -> list[ApplianceInfo]:
        """Get the list of turnkey appliances filtered by the query string."""
        if self.query_string:
            return [apl for apl in self._turnkey_appliances if self.query_string in apl.template.lower()]
        return self._turnkey_appliances

    @rx.var
    def system_appliances(self) -> list[ApplianceInfo]:
        """Get the list of system appliances filtered by the query string."""
        if self.query_string:
            return [apl for apl in self._system_appliances if self.query_string in apl.template.lower()]
        return self._system_appliances

    @rx.event
    async def load(self) -> None:
        """Load available appliances from Proxmox, filtering out existing ones and updating state."""
        self.reset()
        default_node = await self.get_var_value(SelectionDefaults.default_node)
        bases = await self.get_var_value(OrbitLabState.base_appliances)
        existing = [apl.config.template for apl in bases]
        for appliance in await Proxmox().list_appliances():
            if appliance.template in existing:
                continue
            if appliance.is_turnkey:
                self.turnkey_appliances.append(appliance)
            else:
                self.system_appliances.append(appliance)
            self.download_configs[appliance.template] = default_node


class CustomApplianceState(rx.State):
    """State management for custom appliance creation dialog."""

    edit_mode: rx.Field[bool] = rx.field(default=False)
    appliance_id: rx.Field[str] = rx.field(default="")
    form_data: rx.Field[dict] = rx.field(default_factory=dict)
    step_order: rx.Field[list[tailwind.SortableItem]] = rx.field(default_factory=list)
    steps_config: rx.Field[dict[int, WorkflowStep]] = rx.field(default_factory=dict)
    
    uploading: rx.Field[bool] = rx.field(default=False)
    upload_progress: rx.Field[int] = rx.field(default=0)
    script_value: rx.Field[str] = rx.field(default="")
    default_script_value: rx.Field[str] = rx.field(default="")
    files_data: rx.Field[list[FileConfig] | None] = rx.field(default=None)

    @rx.var
    def dialog_title(self) -> str:
        """Return the dialog title based on whether edit mode is enabled."""
        if self.edit_mode:
            return f"Edit Appliance: {self.appliance_id}"
        return "Create Custom Appliance"

    @rx.var
    def step_names_in_order(self) -> list[str]:
        """Get the names of workflow steps in their configured order."""
        return [self.steps_config[step["id"]].name for step in self.step_order]

    @rx.var
    def workflow_steps(self) -> list[WorkflowStep]:
        return [self.steps_config[step["id"]] for step in self.step_order]

    @rx.event
    async def load_appliance(self, appliance_id: str) -> None:
        """Populate the state with data from an existing custom appliance manifest for editing."""
        appliance = await ApplianceClient().get_appliance(appliance_type="custom", id=appliance_id)
        self.appliance_id = appliance.config.id
        self.form_data = appliance.config.model_dump()
        for index, step in enumerate(appliance.config.steps):
            self.step_order.append({"id": index})
            self.steps_config[index] = WorkflowStep.model_validate(step.model_dump())


class DeleteApplianceState(rx.State):
    """State management for deleting a custom appliance, including confirmation logic."""

    appliance_id: str = ""
    appliance_type: Literal["base", "custom"] = "base"
    confirmation: str = ""

    @rx.var
    def delete_disabled(self) -> bool:
        """Return True if the delete action should be disabled (name and confirmation do not match)."""
        return self.appliance_id != self.confirmation
