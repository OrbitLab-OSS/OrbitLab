"""Infrastructure Appliance Workflows."""

import asyncio
from typing import get_args

import backoff

from orbitlab.data_types import OrbitLabApplianceType
from orbitlab.proxmox import Proxmox, ProxmoxAdapter
from orbitlab.redis.clients import BackplaneClient, ClusterClient
from orbitlab.redis.models import InfraAppliance
from .base import Workflow, WorkflowPayload


class InfraAppliancePayload(WorkflowPayload):
    """Download Infrastructure Appliance Payload."""


class DownloadInfraApplianceV1(Workflow):
    """Download Infrastructure Appliances."""

    TYPE: str = "infrastructure.download"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[InfraAppliancePayload] = InfraAppliancePayload
    payload: InfraAppliancePayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        infra = await ClusterClient().get_infra_appliances()
        latest = await Proxmox().get_infrastructure_appliances(await ClusterClient().get_appliances_branch())
        
        if infra.version == latest.version:
            return await self.succeed(f"OrbitLab Infrastructure already at latest version: {latest.version}")

    async def provision(self) -> InfraAppliancePayload:
        """Download the infra appliance, deleting the old one, if necessary."""
        client = ClusterClient()
        proxmox = Proxmox()
        infra = await client.get_infra_appliances()

        await self.log(f"Deleting old appliance versions: {infra.version}")
        await asyncio.gather(*[
            proxmox.delete_appliance(node=old_appliance.node, storage=old_appliance.storage, volume_id=old_appliance.volume_id)
            for old_appliance in infra.appliances.values()
        ])

        appliances = await proxmox.get_infrastructure_appliances(await client.get_appliances_branch())
        defaults = await client.get_defaults()
        for appliance_type in get_args(OrbitLabApplianceType.__value__):
            appliance = appliances.get_appliance(appliance_type=appliance_type)
            if appliance.filename.endswith(".qcow2"):
                storage = defaults.imports
                content = "import"
            else:
                storage = defaults.vztmpl
                content = "vztmpl"
                
            checksum_algorithm, checksum = appliance.digest.split(":")
            params = {
                "content": content,
                "url": appliance.browser_download_url,
                "filename": appliance.filename,
                "checksum": checksum,
                "checksum-algorithm": checksum_algorithm,
            }
            await self.log(f"Downloading {appliance_type} v{appliances.version} with params: {params}")
            volume_id = await proxmox.download_infrastructure_appliance(storage=storage, params=params, node=defaults.node)
            await self.log(f"New {appliance_type} volume ID: {volume_id}")
            infra.appliances[appliance_type] = InfraAppliance(node=defaults.node, volume_id=volume_id)
        
        infra.version = appliances.version
        await client.set_infra_appliances(appliances=infra)
        return await self.succeed(f"Successfully updated infrastructure to version {infra.version}")


class UpgradeBackplancePayload(InfraAppliancePayload):
    vmid: int = 0


class UpgradeBackplaneV1(Workflow):
    """Upgrade Backplane Appliances."""

    TYPE: str = "infrastructure.upgrade-backplane"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[UpgradeBackplancePayload] = UpgradeBackplancePayload
    payload: UpgradeBackplancePayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        infra = await ClusterClient().get_infra_appliances()
        current_version = await BackplaneClient().get_appliance_version()
        
        if infra.version == current_version:
            return await self.succeed(f"Backplane already at latest version: v{current_version}", notify=False)

    @backoff.on_predicate(backoff.fibo, max_time=30, max_tries=10)
    async def _wait_for_relay_probe_ping(self, vmid: int) -> bool:
        if ping := await BackplaneClient().get_relay_ping():
            if ping == vmid:
                await self.log(f"Relay probe pinged: {ping}")
                return True
        return False

    async def provision(self) -> None:
        client = BackplaneClient()
        proxmox = Proxmox()
        guest = await ProxmoxAdapter(proxmox).create_managed_guest(
            resource_id="backplane",
            instance_type="lxc",
            node="",
            parameters=client.generate_backplane_params,
        )
        vmid = guest.vmid

        await asyncio.gather(
            self.log(f"Mounting Redis socket file to new Backplane appliance VMID {vmid}"),
            proxmox.attach_redis_socket_file(vmid=vmid),
        )
        
        await asyncio.gather(
            self.log(f"Starting new Backplane appliance VMID {vmid}"),
            proxmox.start(vmid=vmid),
        )
        
        self.payload.vmid = vmid
        
    async def configure(self) -> None:
        if not self.payload.vmid:
            return await self.fail("New backplane VMID not set in previous phase.")
        
        client = BackplaneClient()
        proxmox = Proxmox()
        
        commands = [
            "systemctl is-active --quiet coredns || exit 1",
            "systemctl is-active --quiet orbital-relay || exit 1",
            "dig @127.0.0.1 ns.orbitlab.internal || exit 1",
            f"curl -X POST http://127.0.0.1/infra/v1/probe --data '{{\"vmid\":{self.payload.vmid}}}' || exit 1",
        ]
        await client.set_relay_ping(vmid=0)
        await self.log(f"Waiting for Backplane appliance VMID {self.payload.vmid} readiness.")
        await proxmox.wait_for_lxc_services(self.payload.vmid, commands)
        
        if not await self._wait_for_relay_probe_ping(vmid=self.payload.vmid):
            return await self.fail("Relay probe did not respond with a valid ping")
    
    async def finalize(self) -> None:
        if not self.payload.vmid:
            return await self.fail("New backplane VMID not set in previous phase.")
        
        client = BackplaneClient()
        
        await asyncio.gather(
            self.log("Terminating old Backplane appliance"),
            Proxmox().terminate(vmid=await client.get_vmid())
        )
        
        infra = await ClusterClient().get_infra_appliances()
        await asyncio.gather(
            self.log("Setting new Backplane metadata"),
            client.set_vmid(vmid=self.payload.vmid),
            client.set_appliance_version(version=infra.version),
        )
class ProbeRelayPayload(InfraAppliancePayload):
    vmid: int


class ProbeRelayV1(Workflow):
    """Upgrade Backplane Appliances."""

    TYPE: str = "infrastructure.probe-relay"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ProbeRelayPayload] = ProbeRelayPayload
    payload: ProbeRelayPayload

    async def validate(self) -> None:
        await BackplaneClient().set_relay_ping(vmid=self.payload.vmid)
        await self.succeed(f"Relay Probe: {self.payload.vmid}", notify=False)
