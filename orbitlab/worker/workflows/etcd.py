import asyncio
from ipaddress import IPv4Interface
from typing import Annotated

from orbitlab.data_types import ETCDStatus, SerializeIP
from orbitlab.proxmox import Proxmox
from orbitlab.proxmox.exceptions import PctExecError
from orbitlab.redis.clients import BackplaneClient, ClusterClient, DNSClient, ETCDClient
from orbitlab.redis.models import ARecord, ETCDMember, SRVRecord
from orbitlab.web.global_state import ETCDState

from .base import Workflow, WorkflowPayload


ETCD_SERVICE_NAME = "ol:service:etcd"


async def check_member_healthy(member: ETCDMember) -> str:
    try:
        async with await Proxmox().create_connection() as connection:
            await connection.lxc_execute_script(vmid=member.vmid, content="/usr/bin/etcd-mgr health-check")
    except PctExecError as err:
        return str(err)
    return ""   


class EtcdPayload(WorkflowPayload):
    """Default ETCD Payload."""


class UpgradeETCDClusterV1(Workflow):
    """Workflow for upgrading the ETCD cluster."""

    TYPE: str = "etcd.upgrade"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[EtcdPayload] = EtcdPayload
    IDP_TOKEN: str = ETCD_SERVICE_NAME
    payload: EtcdPayload

    async def validate(self) -> None:
        """Validate ETCD cluster exists for upgrade."""
        client = ETCDClient()

        if await client.get_version() == (await ClusterClient().get_infra_appliances()).version:
            return await self.succeed("ETCD Cluster already on the latest version.")

        await client.set_status(status=ETCDStatus.UPGRADING)
        await self.emit_reflex_events(ETCDState.cache_clear("status"))

    async def provision(self) -> None:
        """Provision replacement ETCD members."""
        client = ETCDClient()
        dns = DNSClient()
        proxmox = Proxmox()
        
        for member in await client.list_members():
            vmid = await proxmox.get_next_vmid()
            params = await client.generate_create_params(vmid=vmid)
            await asyncio.gather(
                self.log(f"Creating {member.name} replacement with params: {self._redact_params(params)}"),
                proxmox.create_instance(instance_type="lxc", params=params),
            )
            
            new_member = await client.get_member_by_vmid(vmid=vmid)
            record = ARecord(ip=new_member.address.ip)
            await asyncio.gather(
                self.log(f"Adding {new_member.name} DNS record"),
                dns.add_backplane_a_records(new_member.name, record),
            )
            
            await asyncio.gather(
                self.log(f"Giving new member {new_member.name} a 30 second warmup before checking health..."),
                proxmox.start(vmid=vmid),
                asyncio.sleep(30),
            )
            
            await self.log("Checking health of new member.")
            if error := await check_member_healthy(member=member):
                return await self.fail(f"ETCD Member {new_member.name} unhealthy: {error}")
            else:
                await asyncio.gather(
                    self.log(f"New member {new_member.name} healthy"),
                    dns.add_backplane_a_records("etcd", record),
                )
            
            async with await proxmox.create_connection() as connection:
                await asyncio.gather(
                    self.log(f"Removing {member.name} from ETCD cluster"),
                    connection.lxc_execute_script(vmid=new_member.vmid, content=f"etcd-mgr remove {member.name}"),
                )
            
            await asyncio.gather(
                self.log(f"Stopping {member.name} and removing DNS Records."),
                dns.remove_backplane_a_records(member.name, ARecord(ip=member.address.ip)),
                dns.remove_backplane_a_records("etcd", ARecord(ip=member.address.ip)),
                dns.remove_backplane_srv_records("etcd-server", "tcp", SRVRecord(target=member.name, port=2380)),
                dns.remove_backplane_srv_records("etcd-client", "tcp", SRVRecord(target=member.name, port=2379)),
                proxmox.stop(vmid=member.vmid),  # SIGKILL so the member being replaced doesn't failover
            )
            
            await asyncio.gather(
                self.log(f"Terminating {member}"),
                proxmox.terminate(vmid=member.vmid),
                client.remove_member(member=member),
                BackplaneClient().release_assigned_ips(member.address),
            )
            
        latest_version = (await ClusterClient().get_infra_appliances()).version
        await client.set_version(version=latest_version)
        await self.succeed(f"Successfully upgraded ETCD cluster to v{latest_version}")

    async def on_succeed(self) -> None:
        await ETCDClient().set_status(status=ETCDStatus.AVAILABLE)
        await self.emit_reflex_events(ETCDState.cache_clear("status"), ETCDState.cache_clear("version"))


class FailoverPayload(EtcdPayload):
    """Payload for ETCD member failover."""

    name: str
    address: Annotated[IPv4Interface, SerializeIP]


class ETCDMemberFailoverV1(Workflow):
    """Workflow for creating an ETCD cluster."""

    TYPE: str = "etcd.failover"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[FailoverPayload] = FailoverPayload
    IDP_TOKEN: str = ETCD_SERVICE_NAME
    payload: FailoverPayload

    async def validate(self) -> None:
        """Validate ETCD cluster exists for failover."""
        client = ETCDClient()
        
        members = await client.list_members()
        failing_member = next(iter([member for member in members if member.name == self.payload.name]), None)
        if not failing_member:
            return await self.succeed(f"Member {self.payload.name} already deleted", notify=False)
        
        if error := await check_member_healthy(member=failing_member):
            await asyncio.gather(
                self.log(f"ETCD Member {failing_member.name} unhealthy: {error}"),
                client.set_status(status=ETCDStatus.DEGRADED),
            )
            await self.emit_reflex_events(ETCDState.cache_clear("status"))
        else:
            await self.succeed(f"Member {self.payload.name} is healthy", notify=False)

    async def provision(self) -> None:
        """Terminate failing memeber and remove from cluster."""
        client = ETCDClient()
        dns = DNSClient()
        backplane = BackplaneClient()
        proxmox = Proxmox()
        
        members = await client.list_members()
        failing_member = next(iter([member for member in members if member.name == self.payload.name]))
        healthy_member = next(iter([member for member in members if member.name != self.payload.name]))
        
        try:
            async with await Proxmox().create_connection() as connection:
                await asyncio.gather(
                    self.log(f"Removing {failing_member} from ETCD cluster"),
                    connection.lxc_execute_script(
                        vmid=healthy_member.vmid,
                        content=f"/usr/bin/etcd-mgr remove {failing_member.name}",
                    ),
                )
        except PctExecError as err:
            print(vars(err), dir(err))
            raise err
        
        await asyncio.gather(
            self.log(f"Removing DNS records for {failing_member}"),
            dns.remove_backplane_a_records(failing_member.name, ARecord(ip=failing_member.address.ip)),
            dns.remove_backplane_a_records("etcd", ARecord(ip=failing_member.address.ip)),
            dns.remove_backplane_srv_records("etcd-server", "tcp", SRVRecord(target=failing_member.name, port=2380)),
            dns.remove_backplane_srv_records("etcd-client", "tcp", SRVRecord(target=failing_member.name, port=2379)),
        )
        
        await asyncio.gather(
            self.log(f"Deleting {failing_member.name}"),
            proxmox.terminate(vmid=failing_member.vmid),
            backplane.release_assigned_ips(failing_member.address),
            client.remove_member(member=failing_member),
        )
        
    async def configure(self) -> None:
        """Create replacement member."""
        client = ETCDClient()
        dns = DNSClient()
        proxmox = Proxmox()
        
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_create_params(vmid=vmid)
        await self.log(f"Creating ETCD memeber node {vmid} with params: {self._redact_params(params)}")
        await proxmox.create_instance(instance_type="lxc", params=params)
        
        member = await client.get_member_by_vmid(vmid=vmid)
        record = ARecord(ip=member.address.ip)
        await asyncio.gather(
            self.log("Creating A records"),
            dns.add_backplane_a_records(member.name, record),
            dns.add_backplane_a_records("etcd", record),
        )
        
        await asyncio.gather(
            self.log(f"Starting member {member} and starting 45 second warm-up"),
            proxmox.start(vmid=vmid),
            asyncio.sleep(45)
        )
        
        if error := await check_member_healthy(member=member):
            await self.fail(f"ETCD Member {member.name} unhealthy: {error}")
        else:
            await self.succeed(f"Member {member} is healthy.", notify=False)

    async def on_succeed(self) -> None:
        await ETCDClient().set_status(status=ETCDStatus.AVAILABLE)
        await self.emit_reflex_events(ETCDState.cache_clear("status"))
