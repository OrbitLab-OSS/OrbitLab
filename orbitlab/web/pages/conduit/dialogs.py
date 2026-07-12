from typing import Final

import reflex as rx

from orbitlab.data_types import FrontendEvents
from orbitlab.proxmox import Proxmox
from orbitlab.redis.clients import ConduitClient, ETCDClient, SectorClient
from orbitlab.redis.models import ConduitEndpointConfig, ConduitPoolConfig, HealthCheck, Instance
from orbitlab.web import tailwind
from orbitlab.web.global_state import OrbitLabState, SelectOptions
from orbitlab.web.utilities import EventGroup, create_workflow


class CreateConduitPoolDialogState(rx.State):
    sector: rx.Field[str] = rx.field(default="")
    available_instances: rx.Field[list[Instance]] = rx.field(default_factory=list)
    selected_instances: rx.Field[dict[str, int | None]] = rx.field(default_factory=dict)
    port_override: rx.Field[bool] = rx.field(default=False)


class InstanceSelectionTable(tailwind.Table, EventGroup):
    """A table component for adding/removing instances from Conduit Pools."""

    @staticmethod
    @rx.event
    async def add_remove_instance(state: CreateConduitPoolDialogState, instance_id: str) -> None:
        if instance_id not in state.selected_instances:
            state.selected_instances[instance_id] = None
        else:
            del state.selected_instances[instance_id]

    @staticmethod
    @rx.event
    async def set_weight(state: CreateConduitPoolDialogState, instance_id: str, weight: int) -> None:
        state.selected_instances[instance_id] = weight

    @classmethod
    def row(cls, instance: Instance) -> list[rx.el.Td]:
        """Create and return the table row component."""
        return [
            tailwind.Checkbox(on_click=cls.add_remove_instance(instance.config.id)),
            rx.text(instance.config.id),
            rx.text(instance.config.name),
            rx.text(instance.config.type.upper()),
            rx.text(instance.state.vmid),
            rx.cond(
                CreateConduitPoolDialogState.selected_instances.contains(instance.config.id),
                tailwind.Input(
                    type="number",
                    min=1,
                    on_change=lambda weight: cls.set_weight(instance.config.id, weight),
                    class_name="w-3xs"
                ),
            ),
        ]


class CreateConduitPoolDialog(EventGroup):
    
    @staticmethod
    @rx.event
    async def open(state: CreateConduitPoolDialogState) -> FrontendEvents:
        state.reset()
        return tailwind.Dialog.open(CreateConduitPoolDialog.dialog_id)
    
    @staticmethod
    @rx.event
    async def set_sector(state: CreateConduitPoolDialogState, sector: str) -> None:
        if sector:
            state.sector = sector
            instances = await state.get_var_value(OrbitLabState.instances)
            state.available_instances = [instance for instance in instances if instance.config.sector == sector]
    
    @staticmethod
    @rx.event
    async def toggle_port_override(state: CreateConduitPoolDialogState) -> None:
        state.port_override = not state.port_override
    
    @staticmethod
    @rx.event
    async def submit(state: CreateConduitPoolDialogState, form: dict) -> FrontendEvents:
        if not state.selected_instances:
            return rx.toast.error("You must select at least one instance target in your selected Sector.")
        
        if "type" not in form:
            form["type"] = "http"
        form["health_check"] = {
            "path": form["path"],
            "expected_status": form["expected_status"],
            "interval": form["interval"],
            "timeout": form["timeout"],
        }
        form["targets"] = [
            {"instance_id": instance_id, "weight": weight}
            for instance_id, weight in state.selected_instances.items()
        ]
        form["sector_name"] = (await SectorClient().get(id=form["sector"])).config.alias
        form["id"] = await ConduitClient().generate_pool_id()
        config = ConduitPoolConfig.model_validate(form)
        await ConduitClient().set_pool(config=config)
        if error := await create_workflow(name="conduit.pool.create", version="v1", payload={"id": config.id}):
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Creating {config.id}..."),
            CreateConduitPoolDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: CreateConduitPoolDialogState) -> FrontendEvents:
        state.reset()
        return tailwind.Dialog.close(CreateConduitPoolDialog.dialog_id)
    
    dialog_id: Final = "create-conduit-pool-dialog"
    form_id: Final = "create-conduit-pool-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return tailwind.Dialog(
            "Create Conduit Pool",
            rx.el.form(
                tailwind.FieldSet(
                    "Pool Configuration",
                    tailwind.FieldSet.Field(
                        "Name:",
                        tailwind.Input(
                            auto_complete="off",
                            name="name",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Sector:",
                        tailwind.Select(
                            SelectOptions.conduit_enabled_sector_options,
                            name="sector",
                            required=True,
                            class_name="w-full",
                            on_change=cls.set_sector
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Type:",
                        tailwind.Select(
                            SelectOptions.conduit_pool_type_options,
                            default_value="http",
                            name="type",
                            required=True,
                            class_name="w-full",
                            disabled=True,  # TODO: Add support for other options
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Port:",
                        tailwind.Input(
                            type="number",
                            default_value=80,
                            name="port",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Balance:",
                        tailwind.Select(
                            SelectOptions.conduit_pool_balance_options,
                            name="balance",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                ),
                tailwind.FieldSet(
                    "Health Check",
                    tailwind.FieldSet.Field(
                        "Method:",
                        tailwind.Select(
                            SelectOptions.conduit_pool_health_check_methods,
                            default_value="GET",
                            name="method",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Path:",
                        tailwind.Input(
                            default_value="/",
                            name="path",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Expected Status Code:",
                        tailwind.Input(
                            type="number",
                            default_value=200,
                            name="expected_status",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Interval:",
                        tailwind.Input(
                            type="number",
                            default_value=30,
                            name="interval",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Timeout:",
                        tailwind.Input(
                            type="number",
                            default_value=5,
                            name="timeout",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Port:",
                        rx.el.div(
                            tailwind.Input(
                                type="number",
                                name="port",
                                required=CreateConduitPoolDialogState.port_override,
                                disabled=~CreateConduitPoolDialogState.port_override,
                                class_name="w-full",
                            ),
                            tailwind.Checkbox(
                                text="Override",
                                checked=CreateConduitPoolDialogState.port_override,
                                on_click=cls.toggle_port_override,
                            ),
                            class_name="w-full flex items-center space-x-3"
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.submit,
            ),
            InstanceSelectionTable(
                name="Available Instances",
                headers=["", "ID", "Name", "Type", "VMID", "Weight"],
                data=CreateConduitPoolDialogState.available_instances,
                refresh=cls.set_sector(CreateConduitPoolDialogState.sector),
            ),
            rx.el.div(
                tailwind.Buttons.Primary("Submit", form=cls.form_id),
                tailwind.Buttons.Secondary("Close", on_click=tailwind.Dialog.close(cls.dialog_id)),
                class_name="w-full flex space-x-4 justify-end mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-[70vw] h-fit",
        )


class UpdateConduitPoolHealthCheckDialogState(rx.State):
    pool_id: rx.Field[str] = rx.field(default="")
    method: rx.Field[str] = rx.field(default="")
    path: rx.Field[str] = rx.field(default="")
    expected_status: rx.Field[int] = rx.field(default=200)
    interval: rx.Field[int] = rx.field(default=30)
    timeout: rx.Field[int] = rx.field(default=5)
    port: rx.Field[int | None] = None
    port_override: rx.Field[bool] = rx.field(default=False)


class UpdateConduitPoolHealthCheckDialog(EventGroup):
    
    @staticmethod
    @rx.event
    async def open(state: UpdateConduitPoolHealthCheckDialogState, pool_id: str) -> FrontendEvents:
        pool = await ConduitClient().get_pool(pool_id=pool_id)
        state.pool_id = pool_id
        state.method = pool.config.health_check.method
        state.path = pool.config.health_check.path
        state.expected_status = pool.config.health_check.expected_status
        state.interval = pool.config.health_check.interval
        state.timeout = pool.config.health_check.timeout
        if pool.config.health_check.port:
            state.port_override = True
            state.port = pool.config.health_check.port
        else:
            state.port = pool.config.port
        return tailwind.Dialog.open(UpdateConduitPoolHealthCheckDialog.dialog_id)
    
    @staticmethod
    @rx.event
    async def submit(state: UpdateConduitPoolHealthCheckDialogState, form: dict) -> FrontendEvents:
        pool = await ConduitClient().get_pool(pool_id=state.pool_id)
        health_check = HealthCheck.model_validate(form)
        pool.config.health_check = health_check
        await ConduitClient().set_pool(config=pool.config)
        return [
            UpdateConduitPoolHealthCheckDialog.update_health_check(pool.config.id),
            OrbitLabState.cache_clear("conduit_pools"),
            rx.toast.info(f"Updating {pool.config.id} health check..."),
            UpdateConduitPoolHealthCheckDialog.close,
        ]

    @staticmethod
    @rx.event
    async def toggle_port_override(state: UpdateConduitPoolHealthCheckDialogState) -> FrontendEvents:
        state.port_override = not state.port_override

    @staticmethod
    @rx.event(background=True)
    async def update_health_check(_: rx.State, pool_id: str) -> FrontendEvents:
        pool = await ConduitClient().get_pool(pool_id=pool_id)
        etcd_member = await ETCDClient().get_random_member()
        async with await Proxmox().create_connection() as connection:
            await connection.lxc_execute_script(
                vmid=etcd_member.vmid,
                content=pool.config.health_check.generate_config_commands(prefix=pool.prefix),
            )
        return rx.toast.success(f"Updated {pool.config.id} health check")

    @staticmethod
    @rx.event
    async def close(state: UpdateConduitPoolHealthCheckDialogState) -> FrontendEvents:
        state.reset()
        return tailwind.Dialog.close(UpdateConduitPoolHealthCheckDialog.dialog_id)
    
    dialog_id: Final = "update-conduit-pool-health-check-dialog"
    form_id: Final = "update-conduit-pool-health-check-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return tailwind.Dialog(
            f"Update Pool {UpdateConduitPoolHealthCheckDialogState.pool_id} Health Check",
            rx.el.form(
                tailwind.FieldSet(
                    "Health Check",
                    tailwind.FieldSet.Field(
                        "Method:",
                        tailwind.Select(
                            SelectOptions.conduit_pool_health_check_methods,
                            default_value=UpdateConduitPoolHealthCheckDialogState.method,
                            name="method",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Path:",
                        tailwind.Input(
                            default_value=UpdateConduitPoolHealthCheckDialogState.path,
                            auto_complete="off",
                            name="path",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Expected Status Code:",
                        tailwind.Input(
                            type="number",
                            default_value=UpdateConduitPoolHealthCheckDialogState.expected_status,
                            name="expected_status",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Interval:",
                        tailwind.Input(
                            type="number",
                            default_value=UpdateConduitPoolHealthCheckDialogState.interval,
                            name="interval",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Timeout:",
                        tailwind.Input(
                            type="number",
                            default_value=UpdateConduitPoolHealthCheckDialogState.timeout,
                            name="timeout",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Port:",
                        rx.el.div(
                            tailwind.Input(
                                type="number",
                                default_value=UpdateConduitPoolHealthCheckDialogState.port,
                                name="port",
                                required=UpdateConduitPoolHealthCheckDialogState.port_override,
                                disabled=~UpdateConduitPoolHealthCheckDialogState.port_override,
                                class_name="w-full",
                            ),
                            tailwind.Checkbox(
                                text="Override",
                                checked=UpdateConduitPoolHealthCheckDialogState.port_override,
                                on_click=cls.toggle_port_override,
                            ),
                            class_name="w-full flex items-center space-x-3"
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.submit,
            ),
            rx.el.div(
                tailwind.Buttons.Primary("Submit", form=cls.form_id),
                tailwind.Buttons.Secondary("Close", on_click=tailwind.Dialog.close(cls.dialog_id)),
                class_name="w-full flex space-x-4 justify-end mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-[70vw] h-fit",
        )


class DeleteConduitPoolDialogState(rx.State):
    pool: rx.Field[str] = rx.field(default="")
    in_use: rx.Field[bool] = rx.field(default=False)
    delete_disabled: rx.Field[bool] = rx.field(default=True)


class DeleteConduitPoolDialog(EventGroup):
    
    @staticmethod
    @rx.event
    async def open(state: DeleteConduitPoolDialogState, pool: str) -> FrontendEvents:
        state.pool = pool
        state.in_use = await ConduitClient().pool_in_use(pool_id=pool)
        return tailwind.Dialog.open(DeleteConduitPoolDialog.dialog_id)

    @staticmethod
    @rx.event
    async def confirm(state: DeleteConduitPoolDialogState, value: str) -> None:
        state.delete_disabled = state.pool != value

    @staticmethod
    @rx.event
    async def delete(state: DeleteConduitPoolDialogState) -> None:
        if error := await create_workflow(name="conduit.pool.delete", version="v1", payload={"id": state.pool}):
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Deleting Conduit Pool {state.pool}..."),
            DeleteConduitPoolDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: DeleteConduitPoolDialogState) -> None:
        state.reset()
        return tailwind.Dialog.close(DeleteConduitPoolDialog.dialog_id)

    dialog_id: Final = "delete-conduit-pool-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return tailwind.Dialog(
            f"Delete Conduit Pool {DeleteConduitPoolDialogState.pool}",
            rx.el.div(
                rx.cond(
                    DeleteConduitPoolDialogState.in_use,
                    rx.text(
                        f"Conduit Pool {DeleteConduitPoolDialogState.pool} is in use by at least one Endpoint. ",
                        f"You must delete all Endpoints associated with {DeleteConduitPoolDialogState.pool} before "
                        "deleting the Conduit Pool."
                    ),
                    rx.fragment(
                        rx.text(
                            f"You are about to delete Conduit Pool ",
                            rx.el.span(DeleteConduitPoolDialogState.pool, class_name="font-bold"),
                            ". To confirm this action, type in the Conduit Pool ID in the text box below.",
                        ),
                        tailwind.Input(
                            placeholder=DeleteConduitPoolDialogState.pool,
                            auto_complete="off",
                            on_change=cls.confirm,
                        )
                    )
                ),
                class_name="w-full flex-col space-y-6 my-8",
            ),
            rx.el.div(
                rx.cond(
                    DeleteConduitPoolDialogState.in_use,
                    rx.fragment(),
                    tailwind.Buttons.Primary("Confirm", on_click=cls.delete, disabled=DeleteConduitPoolDialogState.delete_disabled),
                ),
                tailwind.Buttons.Secondary("Cancel", on_click=cls.close),
                class_name="w-full flex justify-end space-x-4 my-8",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )


class CreateConduitEndpointDialogState(rx.State):
    name: rx.Field[str] = rx.field(default="")
    sector: rx.Field[str] = rx.field(default="")
    pool_id: rx.Field[str] = rx.field(default="")
    pool_type: rx.Field[str] = rx.field(default="")
    endpoint_type: rx.Field[str] = rx.field(default="")
    port: rx.Field[int | None] = None
    port_disabled: rx.Field[bool] = rx.field(default=False)
    domain: rx.Field[str] = rx.field(default="")
    available_domains: rx.Field[list[str]] = rx.field(default_factory=list)
    host: rx.Field[str] = rx.field(default="")
    host_override: rx.Field[bool] = rx.field(default=False)
    
    @rx.var
    def sector_not_selected(self) -> bool:
        return self.sector == ""
    
    @rx.var
    def endpoint_types(self) -> dict[str, str]:
        if self.pool_type:
            endpoint_types = {
                "HTTP": "http",
                "HTTPS": "https",
                "TCP": "tcp",
                "UDP": "udp"
            }
            return {key: value for key, value in endpoint_types.items() if self.pool_type in value}
        return {}

    @rx.var
    def fqdn(self) -> str:
        if self.host and self.domain:
            return f"{self.host}.{self.domain}"
        return ""


class CreateConduitEndpointDialog(EventGroup):

    @staticmethod
    @rx.event
    async def open(state: CreateConduitEndpointDialogState) -> FrontendEvents:
        state.reset()
        return tailwind.Dialog.open(CreateConduitEndpointDialog.dialog_id)

    @staticmethod
    @rx.event
    async def set_name(state: CreateConduitEndpointDialogState, name: str) -> None:
        state.name = name
        state.host = name.lower()

    @staticmethod
    @rx.event
    async def set_sector(state: CreateConduitEndpointDialogState, sector: str) -> None:
        state.sector = sector
        sector_obj = await SectorClient().get(id=sector)
        state.available_domains = [available.domain for available in sector_obj.config.domains]

    @staticmethod
    @rx.event
    async def set_pool(state: CreateConduitEndpointDialogState, pool_id: str) -> None:
        state.pool_id = pool_id
        pool = await ConduitClient().get_pool(pool_id=pool_id)
        state.pool_type = pool.config.type

    @staticmethod
    @rx.event
    async def set_endpoint_type(state: CreateConduitEndpointDialogState, endpoint_type: str) -> None:
        state.endpoint_type = endpoint_type
        state.port = None
        state.port_disabled = False
        if state.endpoint_type == "http":
            state.port = 80
            state.port_disabled = True
            state.endpoint_type = "http"
        if state.endpoint_type == "https":
            state.port = 443
            state.port_disabled = True
            state.endpoint_type = "https"

    @staticmethod
    @rx.event
    async def set_domain(state: CreateConduitEndpointDialogState, domain: str) -> None:
        state.domain = domain

    @staticmethod
    @rx.event
    async def toggle_host_override(state: CreateConduitEndpointDialogState) -> None:
        state.host_override = not state.host_override
        if state.host_override:
            state.host = ""
        else:
            state.host = state.name.lower()

    @staticmethod
    @rx.event
    async def set_host(state: CreateConduitEndpointDialogState, value: str) -> None:
        if state.host_override:
            state.host = value.lower()

    @staticmethod
    @rx.event
    async def submit(state: CreateConduitEndpointDialogState, form: dict) -> FrontendEvents:
        if "host" not in form:
            form["host"] = str(form["name"]).lower()
        
        client = ConduitClient()
        pool = await client.get_pool(pool_id=form["pool"])
        
        form["id"] = await client.generate_endpoint_id()
        form["sector_name"] = (await SectorClient().get(id=form["sector"])).config.alias
        form["pool_name"] = pool.config.name
        form["port"] = state.port
        form["rules"] = [{"host": ".".join([form["host"], form["domain"]])}]
        
        config = ConduitEndpointConfig.model_validate(form)
        await client.set_endpoint(config=config)
        
        if error := await create_workflow(name="conduit.endpoint.create", version="v1", payload={"id": config.id}):
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Creating {config.id}..."),
            CreateConduitEndpointDialog.close,
        ]
    
    @staticmethod
    @rx.event
    async def close(state: CreateConduitEndpointDialogState) -> FrontendEvents:
        state.reset()
        return tailwind.Dialog.close(CreateConduitEndpointDialog.dialog_id)

    dialog_id: Final = "create-conduit-endpoint-dialog"
    form_id: Final = "create-conduit-endpoint-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return tailwind.Dialog(
            "Create Conduit Endpoint",
            rx.el.form(
                tailwind.FieldSet(
                    "Endpoint Configuration",
                    tailwind.FieldSet.Field(
                        "Name:",
                        tailwind.Input(
                            on_change=cls.set_name,
                            auto_complete="off",
                            name="name",
                            required=True,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Sector:",
                        tailwind.Select(
                            SelectOptions.conduit_enabled_sector_options,
                            name="sector",
                            required=True,
                            class_name="w-full",
                            on_change=cls.set_sector
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Pool:",
                        tailwind.Select(
                            SelectOptions.conduit_pool_options.get(CreateConduitEndpointDialogState.sector, {}),
                            on_change=cls.set_pool,
                            name="pool",
                            required=True,
                            disabled=CreateConduitEndpointDialogState.sector_not_selected,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Type:",
                        tailwind.Select(
                            CreateConduitEndpointDialogState.endpoint_types,
                            value=CreateConduitEndpointDialogState.endpoint_type,
                            on_change=cls.set_endpoint_type,
                            name="type",
                            required=True,
                            disabled=CreateConduitEndpointDialogState.sector_not_selected,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Port:",
                        tailwind.Input(
                            type="number",
                            value=CreateConduitEndpointDialogState.port,
                            name="port",
                            required=True,
                            class_name="w-full",
                            disabled=True
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Domain:",
                        tailwind.Select(
                            CreateConduitEndpointDialogState.available_domains,
                            on_change=cls.set_domain,
                            name="domain",
                            required=True,
                            disabled=CreateConduitEndpointDialogState.sector_not_selected,
                            class_name="w-full",
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Host:",
                        rx.el.div(
                            tailwind.Input(
                                value=CreateConduitEndpointDialogState.host,
                                auto_complete="off",
                                on_change=cls.set_host,
                                name="host",
                                required=CreateConduitEndpointDialogState.host_override,
                                disabled=~CreateConduitEndpointDialogState.host_override,
                                class_name="w-full",
                            ),
                            tailwind.Checkbox(
                                text="Override",
                                checked=CreateConduitEndpointDialogState.host_override,
                                on_click=cls.toggle_host_override,
                            ),
                            class_name="w-full flex items-center space-x-3"
                        ),
                    ),
                    tailwind.FieldSet.Field(
                        "Endpoint:",
                        tailwind.Input(
                            value=CreateConduitEndpointDialogState.fqdn,
                            disabled=True,
                            class_name="w-full",
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.submit,
            ),
            rx.el.div(
                tailwind.Buttons.Primary("Submit", form=cls.form_id),
                tailwind.Buttons.Secondary("Close", on_click=tailwind.Dialog.close(cls.dialog_id)),
                class_name="w-full flex space-x-4 justify-end mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[75vw] w-[70vw] h-fit",
        )


class DeleteConduitEndpointDialogState(rx.State):
    endpoint_id: rx.Field[str] = rx.field(default="")
    delete_disabled: rx.Field[bool] = rx.field(default=True)


class DeleteConduitEndpointDialog(EventGroup):

    @staticmethod
    @rx.event
    async def open(state: DeleteConduitEndpointDialogState, endpoint_id: str) -> FrontendEvents:
        state.endpoint_id = endpoint_id
        return tailwind.Dialog.open(DeleteConduitEndpointDialog.dialog_id)

    @staticmethod
    @rx.event
    async def confirm(state: DeleteConduitEndpointDialogState, value: str) -> None:
        state.delete_disabled = state.endpoint_id != value

    @staticmethod
    @rx.event
    async def delete(state: DeleteConduitEndpointDialogState) -> None:
        if error := await create_workflow(name="conduit.delete", version="v1", payload={"id": state.endpoint_id}):
            return rx.toast.error(error)
        return [
            rx.toast.info(f"Deleting {state.endpoint_id}..."),
            DeleteConduitEndpointDialog.close,
        ]

    @staticmethod
    @rx.event
    async def close(state: DeleteConduitEndpointDialogState) -> FrontendEvents:
        state.reset()
        return tailwind.Dialog.close(DeleteConduitEndpointDialog.dialog_id)

    dialog_id: Final = "delete-conduit-endpoint-dialog"
    
    def __new__(cls) -> rx.Component:
        """Create and return the dialog component."""
        return tailwind.Dialog(
            f"Delete Conduit Endpoint {DeleteConduitEndpointDialogState.endpoint_id}",
            rx.el.div(
                rx.text(
                    f"You are about to delete Conduit Endpoint ",
                    rx.el.span(DeleteConduitEndpointDialogState.endpoint_id, class_name="font-bold"),
                    ". To confirm this action, type in the Conduit Endpoint ID in the text box below.",
                ),
                tailwind.Input(
                    placeholder=DeleteConduitEndpointDialogState.endpoint_id,
                    auto_complete="off",
                    on_change=cls.confirm,
                ),
                class_name="w-full flex flex-col space-y-10",
            ),
            rx.el.div(
                tailwind.Buttons.Primary("Delete", on_click=cls.delete, disabled=DeleteConduitEndpointDialogState.delete_disabled),
                tailwind.Buttons.Secondary("Close", on_click=tailwind.Dialog.close(cls.dialog_id)),
                class_name="w-full flex space-x-4 justify-end mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="max-w-[40vw] w-fit",
        )


class Dialogs:
    def __new__(cls) -> rx.Component:
        return rx.fragment(
            CreateConduitPoolDialog(),
            UpdateConduitPoolHealthCheckDialog(),
            DeleteConduitPoolDialog(),
            CreateConduitEndpointDialog(),
            DeleteConduitEndpointDialog(),
        )
