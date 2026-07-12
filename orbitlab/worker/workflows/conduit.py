import asyncio
import json
from typing import Literal

from pydantic import BaseModel

from orbitlab.proxmox import Proxmox
from orbitlab.redis.clients import ConduitClient, DNSClient, ETCDClient, InstanceClient, SectorClient
from orbitlab.redis.models import ARecord
from orbitlab.web.global_state import OrbitLabState

from .base import Workflow, WorkflowPayload


class ConduitPayload(WorkflowPayload):
    """Payload for Conduit workflows."""

    id: str


class ConduitPoolCreateV1(Workflow):
    """Workflow for creating a Conduit Pool (Traefik Service)."""

    TYPE: str = "conduit.pool.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ConduitPayload] = ConduitPayload
    payload: ConduitPayload

    async def validate(self) -> None:
        """Validate if pool does not exist."""
        client = ConduitClient()
        if not await client.pool_exists(pool_id=self.payload.id):
            return await self.fail(f"Conduit Pool {self.payload.id} does not exist")
        
        await self.emit_reflex_events(OrbitLabState.cache_clear("conduit_pools"))

    async def provision(self) -> None:
        client = ConduitClient()
        dns = DNSClient()
        instances = InstanceClient()
        proxmox = Proxmox()
        pool = await client.get_pool(pool_id=self.payload.id)
        
        for target in pool.config.targets:
            instance = await instances.get_instance(id=target.instance_id)
            if not instance.state.address:
                return await self.fail(f"Target instance {target} has no address.")
            record = ARecord(ip=instance.state.address)
            await asyncio.gather(
                self.log(f"Adding target DNS A Record for target {target}: {record}"),
                dns.add_sector_a_records(pool.config.sector, instance.config.id, record)
            )
        
        etcd_member = await ETCDClient().get_random_member()
        async with await proxmox.create_connection() as connection:
            await asyncio.gather(
                self.log(f"Using VMID {etcd_member.vmid} to create {self.payload.id}"),
                connection.lxc_execute_script(
                    vmid=etcd_member.vmid,
                    content=pool.generate_config_commands(),
                )
            )


class ConduitEndpointCreateV1(Workflow):
    """Workflow for creating a Conduit Endpoint (Traefik Router)."""

    TYPE: str = "conduit.endpoint.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ConduitPayload] = ConduitPayload
    payload: ConduitPayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        client = ConduitClient()
        if not await client.endpoint_exists(endpoint_id=self.payload.id):
            return await self.fail(f"Conduit Endpoint {self.payload.id} does not exist")
        
        await self.emit_reflex_events(OrbitLabState.cache_clear("conduit_endpoints"))

    async def provision(self) -> None:
        client = ConduitClient()
        proxmox = Proxmox()
        endpoint = await client.get_endpoint(endpoint_id=self.payload.id)
        sector = await SectorClient().get(id=endpoint.config.sector)
        cert_resolver = sector.get_cert_resolver(domain=endpoint.config.domain)
        
        etcd_member = await ETCDClient().get_random_member()
        async with await proxmox.create_connection() as connection:
            await asyncio.gather(
                self.log(f"Using VMID {etcd_member.vmid} to create endpoint {self.payload.id}"),
                connection.lxc_execute_script(
                    vmid=etcd_member.vmid,
                    content=endpoint.config.generate_config_commands(cert_resolver=cert_resolver),
                )
            )
        
        await client.add_endpoint_association(endpoint_id=self.payload.id)

    async def on_succeed(self) -> None:
        await self.emit_reflex_events(
            OrbitLabState.cache_clear("conduit_endpoints"),
            OrbitLabState.cache_clear("conduit_pools"),
        )


class Target(BaseModel):
    service: str
    url: str
    name: str
    status: Literal["UP", "DOWN"]

    @property
    def pool_id(self) -> str:
        return self.service.replace("@etcd", "")


class ConduitHealthPayload(ConduitPayload):
    """Payload for Conduit health telemetry."""

    targets: list[Target]


class ConduitHealthV1(Workflow):
    """Workflow for creating a Conduit Endpoint (HAproxy)."""

    TYPE: str = "conduit.health"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ConduitHealthPayload] = ConduitHealthPayload
    payload: ConduitHealthPayload
    
    async def validate(self) -> None:
        sector_id = self.payload.id.replace("conduit-", "")
        if not await SectorClient().get_vmid(id=sector_id, appliance="conduit"):
            return await self.fail(f"Conduit for Sector {sector_id} does not exist")
        
        if not self.payload.targets:
            return await self.succeed(f"No targets for which to report health in {self.payload.id}", notify=False)
        
    async def provision(self) -> None:
        client = ConduitClient()
        
        for target in self.payload.targets:
            await self.log(f"Conduit {self.payload.id} target {target.name} -> {target.status}")
            await client.set_target_health(pool_id=target.pool_id, target_id=target.name, status=target.status)

        await self.emit_reflex_events(OrbitLabState.cache_clear("conduit_pools"))
        return await self.succeed(f"Updated target health statuses for {self.payload.id}", notify=False)


class ConduitPoolDeleteV1(Workflow):
    """Workflow for deleting a Conduit Endpoint (HAproxy)."""

    TYPE: str = "conduit.pool.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ConduitPayload] = ConduitPayload
    payload: ConduitPayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        client = ConduitClient()
        if not await client.pool_exists(pool_id=self.payload.id):
            return await self.succeed(f"Conduit Pool {self.payload.id} does not exist")
        
    async def provision(self) -> None:
        client = ConduitClient()
        dns = DNSClient()
        proxmox = Proxmox()
        pool = await client.get_pool(pool_id=self.payload.id)
        
        etcd_member = await ETCDClient().get_random_member()
        async with await proxmox.create_connection() as connection:
            await asyncio.gather(
                self.log(f"Using VMID {etcd_member.vmid} to delete {pool.config.id} config"),
                connection.lxc_execute_script(
                    vmid=etcd_member.vmid,
                    content=f"etcdctl del --prefix {pool.prefix}",
                )
            )

        await asyncio.gather(
            self.log(f"Deleting Sector DNS A Records for {pool.config.id} targets"),
            *[
                dns.delete_sector_a_record(
                    sector_id=pool.config.sector,
                    hostname=target.instance_id,
                ) for target in pool.config.targets
            ]
        )

        await asyncio.gather(
            self.log(f"Deleting Conduit {pool.config.id}"),
            client.delete_pool(pool_id=pool.config.id),
        )

        await self.succeed(f"Deleted Conduit {pool.config.id}")

    async def on_succeed(self) -> None:
        """Update sector in frontend."""
        await self.emit_reflex_events(OrbitLabState.cache_clear("conduit_pools"))


class ConduitDeleteV1(Workflow):
    """Workflow for deleting a Conduit Endpoint (Traefik Router)."""

    TYPE: str = "conduit.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ConduitPayload] = ConduitPayload
    payload: ConduitPayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        client = ConduitClient()
        if not await client.endpoint_exists(endpoint_id=self.payload.id):
            return await self.succeed(f"Conduit Endpoint {self.payload.id} does not exist")
        
    async def provision(self) -> None:
        client = ConduitClient()
        endpoint = await client.get_endpoint(endpoint_id=self.payload.id)
        
        etcd_member = await ETCDClient().get_random_member()
        async with await Proxmox().create_connection() as connection:
            await asyncio.gather(
                self.log(f"Using VMID {etcd_member.vmid} to create endpoint {self.payload.id}"),
                connection.lxc_execute_script(
                    vmid=etcd_member.vmid,
                    content="\n".join([
                        f"etcdctl del {endpoint.config.prefix}/{endpoint.config.id}-http",
                        f"etcdctl del {endpoint.config.prefix}/{endpoint.config.id}-https",
                    ]),
                )
            )
        
        await client.delete_endpoint(endpoint_id=self.payload.id)

    async def on_succeed(self) -> None:
        await self.emit_reflex_events(OrbitLabState.cache_clear("conduit_endpoints"))
