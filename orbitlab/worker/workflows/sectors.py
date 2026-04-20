"""Sector Workflows."""

from orbitlab.data_types import SectorStatus
from orbitlab.proxmox import ProxmoxCompute, ProxmoxNetworks
from orbitlab.redis.clients import BackplaneClient, SectorClient
from orbitlab.web.global_state import OrbitLabState

from .base import Workflow, WorkflowPayload


class SectorPayload(WorkflowPayload):
    """Create Network Sector Payload."""

    id: str


class CreateSectorV1(Workflow):
    """Create Network Sector."""

    TYPE: str = "sector.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[SectorPayload] = SectorPayload
    payload: SectorPayload

    async def validate(self) -> None:
        """Validate the sector gateway, if VMID already assigned proceed to finalize."""
        if not await SectorClient().sector_exists():
            await self.fail(f"Sector manifest {self.payload.id} does not exist")
            return

        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("sectors")])

    async def provision(self) -> None:
        """Provision the new sector."""
        sector = await SectorClient().get(id=self.payload.id)
        backplane = await BackplaneClient().get()
        proxmox = ProxmoxNetworks()
        
        zone_params = {
            "type": "vxlan",
            "zone": sector.config.bridge,
            "peers": ",".join([str(peer) for peer in backplane.controller.peers]),
            "mtu": backplane.mtu,
        }
        await self.log(f"Creating Sector VXLAN Zone with params: {zone_params}.")
        await proxmox.create(path="/cluster/sdn/zones", model=None, **zone_params)
        
        vnet_params = {
            "vnet": sector.config.bridge,
            "zone": sector.config.bridge,
            "alias": sector.config.alias,
            "tag": sector.config.tag,
        }
        await self.log(f"Creating Sector VNet with params: {vnet_params}.")
        await proxmox.create("/cluster/sdn/vnets", model=None, **vnet_params)
        
        subnet_params = {
            "subnet": sector.config.cidr_block.with_prefixlen,
            "gateway": str(sector.config.default_gateway.ip),
            "type": "subnet",
        }
        await self.log(f"Creating Sector Subnet with params: {subnet_params}.")
        await proxmox.create(f"/cluster/sdn/vnets/{sector.config.bridge}/subnets", model=None, **subnet_params)
        
        await self.log(f"Applying SDN configuration...")
        await proxmox.set(path="/cluster/sdn")

    async def configure(self) -> None:
        """Create and configure the sector gateway appliance."""
        client = SectorClient()
        proxmox = ProxmoxCompute()
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_gateway_params(id=self.payload.id, vmid=vmid)
        
        await self.log(f"Creating Sector gateway {vmid} with params: {self._redact_params(params=params)}.")
        await proxmox.create_lxc(params=params)
        await proxmox.start(vmid=vmid)

    async def on_succeed(self) -> None:
        """Mark sector as available."""
        await SectorClient().set_sector_status(id=self.payload.id, status=SectorStatus.AVAILABLE)
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("sectors")])


class DeleteSectorV1(Workflow):
    """Delete a Sector."""

    TYPE: str = "sector.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[SectorPayload] = SectorPayload
    payload: SectorPayload

    async def validate(self) -> None:
        """Validate the sector exists."""
        if not await SectorClient().sector_exists():
            return await self.succeed(f"Sector {self.payload.id} doesn't exist or already deleted.")

    async def provision(self) -> None:
        """Delete the sector and appliance."""
        proxmox = ProxmoxCompute()
        sector = await SectorClient().get(id=self.payload.id)
        
        if sector.state.gateway_vmid:
            await self.log(f"Terminating sector gateway {sector.state.gateway_vmid}")
            await proxmox.terminate(vmid=sector.state.gateway_vmid)
            
        subnet_id = str(sector.config.cidr_block).replace("/", "-")
        await self.log(f"Deleting sector subnet {subnet_id}")
        await proxmox.delete(
            path=f"/cluster/sdn/vnets/{sector.config.bridge}/subnets/{sector.config.bridge}-{subnet_id}",
            model=None,
        )
        
        await self.log(f"Deleting sector vnet {sector.config.bridge}")
        await proxmox.delete(path=f"/cluster/sdn/vnets/{sector.config.bridge}", model=None)
        
        await self.log(f"Deleting sector zone {sector.config.bridge}")
        await proxmox.delete(path=f"/cluster/sdn/zones/{sector.config.bridge}", model=None)
        
        await self.log("Applying SDN deletion changes...")
        await proxmox.set(path="/cluster/sdn")
        
        await SectorClient().delete(id=self.payload.id)
        await self.succeed(f"Sector {self.payload.id} deleted.")

    async def on_succeed(self) -> None:
        """Delete the state from Redis."""
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("sectors")])

    async def on_failure(self) -> None:
        """Actions to perform on workflow failure."""
        await self.emit_reflex_events(events=[OrbitLabState.cache_clear("sectors")])
