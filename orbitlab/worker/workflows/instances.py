"""Instance Workflows."""

import asyncio
from ipaddress import IPv4Address, IPv4Interface
from typing import Annotated, Literal

from pydantic import computed_field

from orbitlab import data_types
from orbitlab.data_types import ComputeStatus, ProxmoxComputeStatus, SerializeIP, ServiceType
from orbitlab.proxmox import Proxmox
from orbitlab.redis.clients import DNSClient, DockFSClient, InstanceClient, SectorClient
from orbitlab.web.global_state import OrbitLabState

from .base import Workflow, WorkflowPayload


class InstancePayload(WorkflowPayload):
    """Payload for Instance workflows."""

    id: str


class InstanceCreateV1(Workflow):

    TYPE: str = "instance.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[InstancePayload] = InstancePayload
    payload: InstancePayload

    async def validate(self) -> None:
        """Validate the LXC manifest and ensure it is not already assigned a VMID."""
        if not await InstanceClient().instance_exists(id=self.payload.id):
            return await self.fail(f"Instance {self.payload.id} does not exist")
        await self.emit_reflex_events(OrbitLabState.cache_clear("instances"))

    async def provision(self) -> None:
        """Provision the LXC container."""
        client = InstanceClient()
        proxmox = Proxmox()
        instance = await client.get_instance(id=self.payload.id)
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_create_params(id=self.payload.id, vmid=vmid)
        
        await asyncio.gather(
            self.log(f"Creating {self.payload.id} {vmid}@{instance.config.node} with params: {self._redact_params(params)}"),
            proxmox.create_instance(instance_type=instance.config.type, params=params, node=instance.config.node),
        )
        await client.set_instance_vmid(id=self.payload.id, vmid=vmid)
        
        if instance.config.type == "qemu":
            await self.log(message=f"Resizing scsi0 on {vmid}@{instance.config.node} to: {instance.config.disk_size}G")
            await asyncio.sleep(1)  # Take a beat so Proxmox doesn't panic when trying to resize the disk after creation
            await proxmox.resize_disk(vmid=vmid, disk_size=instance.config.disk_size, disk_id="scsi0")
        
        # Set the status now, so we can be sure it's set before we emit the Reflex update event.
        await client.set_instance_status(id=self.payload.id, status=ComputeStatus.STARTING)
        await asyncio.gather(
            self.log(f"Starting {self.payload.id} {vmid}@{instance.config.node}"),
            self.emit_reflex_events(OrbitLabState.cache_clear("instances")),
            proxmox.start(vmid=vmid),
        )

    async def finalize(self) -> None:
        """Finalize the LXC container creation by retrieving and storing its IPv4 address."""
        await asyncio.gather(
            InstanceClient().set_instance_status(id=self.payload.id, status=ComputeStatus.RUNNING),
            self._create_new_workflow(workflow=AquireInstanceIpAddress, payload=self.payload.copy_payload()),
        )
        await self.emit_reflex_events(OrbitLabState.cache_clear("instances"))


class AquireInstanceIpAddress(Workflow):
    """Workflow for acquiring an IPv4 address for a VM instance."""

    TYPE: str = "instance.acquire-ip"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[InstancePayload] = InstancePayload
    payload: InstancePayload

    async def validate(self) -> None:
        """Validate that the VM has qemu guest agent enabled."""
        client = InstanceClient()
        
        if not await client.instance_exists(id=self.payload.id):
            return await self.fail(f"Instance {self.payload.id} does not exist.")
        
        instance = await client.get_instance(id=self.payload.id)
        if instance.config.type == "qemu" and not await Proxmox().get_agent_enabled(vmid=instance.state.vmid): 
            await self.fail(error=f"Guest Agent not enabled for {self.payload.id}")

    async def provision(self) -> None:
        client = InstanceClient()
        proxmox = Proxmox()
        
        instance = await client.get_instance(id=self.payload.id)
        max_retries = 3
        retries = 0
        while retries < max_retries:
            if address := await proxmox.get_ipv4_address(vmid=instance.state.vmid):
                await asyncio.gather(
                    client.set_instance_address(id=self.payload.id, address=address.ip),
                    DNSClient().add_instance_dhcp_record(sector_id=instance.config.sector, address=address.ip),
                )
                return 
            retries += 1
            await self.log(level="Info", message=f"Acquiring IPv4 address for {self.payload.id} retry {retries}")
        await self.fail(error=f"Max retries exceeded attempting to aquire IPv4 address for {self.payload.id}")

    async def on_succeed(self) -> None:
        """Handle actions to perform when the workflow succeeds."""
        await self.emit_reflex_events(OrbitLabState.cache_clear("instances"))


class InstanceStateChangePayload(InstancePayload):
    """Payload for Instance State Change workflows."""

    desired_status: ProxmoxComputeStatus


class InstanceStateChangeV1(Workflow):
    """Workflow for changing the state of an LXC container."""

    TYPE: str = "instance.state-change"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[InstanceStateChangePayload] = InstanceStateChangePayload
    payload: InstanceStateChangePayload

    async def validate(self) -> None:
        """Validate the current state of the LXC container and ensure the desired state change is possible."""
        client = InstanceClient()
        
        if not await client.instance_exists(id=self.payload.id):
            return await self.fail(f"Instance {self.payload.id} does not exist.")

        instance = await client.get_instance(id=self.payload.id)
        status = await Proxmox().get_status(vmid=instance.state.vmid)
        if self.payload.desired_status in (ProxmoxComputeStatus.STOP, ProxmoxComputeStatus.SHUTDOWN) and status == "stopped":
            await client.set_instance_status(id=self.payload.id, status=ComputeStatus.STOPPED)
            await self.emit_reflex_events(OrbitLabState.cache_clear("instances"))
            return await self.succeed(f"VMID {instance.state.vmid} already stopped.")
            
        if self.payload.desired_status == ProxmoxComputeStatus.START and status == "running":
            await client.set_instance_status(id=self.payload.id, status=ComputeStatus.RUNNING)
            await self.emit_reflex_events(OrbitLabState.cache_clear("instances"))
            return await self.succeed(f"VMID {instance.state.vmid} already running.")
        
        await client.set_instance_status(id=self.payload.id, status=ProxmoxComputeStatus.get_state(status=self.payload.desired_status))
        await self.emit_reflex_events(OrbitLabState.cache_clear("instances"))

    async def provision(self) -> None:
        """Change the state of the LXC container to the desired state."""
        instance = await InstanceClient().get_instance(id=self.payload.id)
        match self.payload.desired_status:
            case ProxmoxComputeStatus.STOP:
                await Proxmox().stop(vmid=instance.state.vmid)
                await InstanceClient().set_instance_status(id=self.payload.id, status=data_types.ComputeStatus.STOPPED)
            case ProxmoxComputeStatus.SHUTDOWN:
                await Proxmox().shutdown(vmid=instance.state.vmid)
                await InstanceClient().set_instance_status(id=self.payload.id, status=data_types.ComputeStatus.STOPPED)
            case ProxmoxComputeStatus.START:
                await Proxmox().start(vmid=instance.state.vmid)
                await InstanceClient().set_instance_status(id=self.payload.id, status=data_types.ComputeStatus.RUNNING)
            case ProxmoxComputeStatus.REBOOT:
                await Proxmox().reboot(vmid=instance.state.vmid)
                await InstanceClient().set_instance_status(id=self.payload.id, status=data_types.ComputeStatus.RUNNING)
            case ProxmoxComputeStatus.TERMINATE:
                await Proxmox().terminate(vmid=instance.state.vmid)

    async def finalize(self) -> None:
        """Finalize the state change of the LXC container and clean up if terminated."""
        if self.payload.desired_status == ProxmoxComputeStatus.TERMINATE:
            instance = await InstanceClient().get_instance(id=self.payload.id)
            await asyncio.gather(
                InstanceClient().delete_instance(id=self.payload.id),
                DNSClient().delete_instance_dhcp_record(sector_id=instance.config.sector, address=instance.state.address),
            )
        await self.emit_reflex_events(OrbitLabState.cache_clear("instances"))


class DHCPPayload(WorkflowPayload):
    """Payload for DHCP event workflow."""

    sector: str
    action: Literal["add", "old"]
    mac: str
    address: Annotated[IPv4Address, SerializeIP]
    host: str = "" # TODO: Remove once Infra has be re-baselined. We no longer care about the on-instance hostname.
    instance_id: str = ""

    @computed_field
    @property
    def service_type(self) -> ServiceType:
        return ServiceType.get_service_type_by_mac(self.mac)


class InstanceDHCPChange(Workflow):
    TYPE: str = "instance.dhcp"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[DHCPPayload] = DHCPPayload
    payload: DHCPPayload

    async def validate(self) -> None:
        if self.payload.service_type == ServiceType.INSTANCE and not await InstanceClient().get_instance_by_mac(mac=self.payload.mac):
            await self.succeed(f"Instance with mac {self.payload.mac} no longer exists", notify=False)
    
    async def configure(self) -> None:
        if self.payload.service_type == ServiceType.INSTANCE:
            instance = await InstanceClient().get_instance(id=self.payload.instance_id)
            if instance.state.address == self.payload.address:
                return await self.succeed(
                    f"Address {instance.state.address} did not change for instance {instance.config.id}.",
                    notify=False,
                )
            if instance.state.address:
                # Delete stale record
                await DNSClient().delete_instance_dhcp_record(sector_id=self.payload.sector, address=instance.state.address)
            await asyncio.gather(
                DNSClient().add_instance_dhcp_record(sector_id=self.payload.sector, address=self.payload.address),
                InstanceClient().set_instance_address(id=instance.config.id, address=self.payload.address),
            )
            await self.emit_reflex_events(OrbitLabState.cache_clear("instances"))
        elif self.payload.service_type == ServiceType.DOCKFS:
            dockfs = DockFSClient()
            cluster_id = await dockfs.get_cluster_id_by_mac(mac=self.payload.mac)
            if not cluster_id:
                return await self.succeed(f"DockFS cluster for node {self.payload} no longer exists", notify=False)
            cluster = await dockfs.get_dockfs(id=cluster_id)
            node_type, cluster_node = cluster.get_node_by_mac(mac=self.payload.mac)
            if not cluster_node:
                return await self.succeed(f"DockFS cluster {cluster_id} node {self.payload.address} no longer exists", notify=False)
            if cluster_node.address and cluster_node.address.ip == self.payload.address:
                return await self.succeed(f"DockFS cluster {cluster_id} node {self.payload.address} no change", notify=False)
            sector = await SectorClient().get(id=self.payload.sector)
            cluster_node.address = IPv4Interface(f"{self.payload.address}/{sector.config.cidr_block.prefixlen}")
            await asyncio.gather(
                self.log(f"Updating cluster {cluster_id} {node_type.capitalize()} node address to {self.payload.address}"),
                dockfs.set_node(id=cluster_id, node=cluster_node, node_type=node_type),
            )
