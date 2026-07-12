"""Sector Workflows."""

import asyncio
from ipaddress import IPv4Interface
import json

from pydantic import Field

from orbitlab.data_types import SectorStatus, WardLinkKeyPair, WardLinkStatus
from orbitlab.proxmox import Proxmox
from orbitlab.redis.clients import BackplaneClient, ClusterClient, DNSClient, ETCDClient, SecretsClient, SectorClient
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
        if not await SectorClient().sector_exists(id=self.payload.id):
            await self.fail(f"Sector manifest {self.payload.id} does not exist")
            return

        await self.emit_reflex_events(OrbitLabState.cache_clear("sectors"))

    async def provision(self) -> None:
        """Provision the new sector."""
        sector = await SectorClient().get(id=self.payload.id)
        backplane = await BackplaneClient().get()
        proxmox = Proxmox()
        
        zone_params = {
            "type": "vxlan",
            "zone": sector.config.bridge,
            "fabric": "OrbitLab",
            "mtu": backplane.config.mtu,
        }
        await asyncio.gather(
            self.log(f"Creating Sector VXLAN Zone with params: {zone_params}."),
            proxmox.create(path="/cluster/sdn/zones", model=None, **zone_params),
        )
        
        vnet_params = {
            "vnet": sector.config.bridge,
            "zone": sector.config.bridge,
            "alias": sector.config.alias,
            "tag": sector.config.tag,
        }
        await asyncio.gather(
            self.log(f"Creating Sector VNet with params: {vnet_params}."),
            proxmox.create(path="/cluster/sdn/vnets", model=None, **vnet_params),
        )
        
        subnet_params = {
            "subnet": sector.config.cidr_block.with_prefixlen,
            "gateway": str(sector.config.default_gateway.ip),
            "type": "subnet",
        }
        await asyncio.gather(
            self.log(f"Creating Sector Subnet with params: {subnet_params}."),
            proxmox.create(path=f"/cluster/sdn/vnets/{sector.config.bridge}/subnets", model=None, **subnet_params),
        )
        
        await asyncio.gather(
            self.log(f"Applying SDN configuration..."),
            proxmox.set(path="/cluster/sdn"),
        )

    async def configure(self) -> None:
        """Create and configure the sector gateway appliance."""
        client = SectorClient()
        proxmox = Proxmox()
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_params(id=self.payload.id, vmid=vmid, appliance="gateway")
        
        await asyncio.gather(
            self.log(f"Creating Sector gateway {vmid} with params: {self._redact_params(params=params)}."),
            proxmox.create_instance(instance_type="lxc", params=params),
        )
        await asyncio.gather(
            self.log("Setting Gateway VMID, Starting Gateway, and Creating DNS Zone"),
            client.set_vmid(id=self.payload.id, appliance="gateway", vmid=vmid),
            proxmox.start(vmid=vmid),
            DNSClient().create_sector_zone(sector_id=self.payload.id),
        )

    async def on_succeed(self) -> None:
        """Mark sector as available."""
        await SectorClient().set_sector_status(id=self.payload.id, status=SectorStatus.AVAILABLE)
        await self.emit_reflex_events(OrbitLabState.cache_clear("sectors"))


class SectorConduitCreateV1(Workflow):
    """Workflow for creating a Sector Conduit (Traefik)."""
    
    TYPE: str = "sector.conduit.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[SectorPayload] = SectorPayload
    payload: SectorPayload
    
    async def validate(self) -> None:
        """Validate if pool does not exist."""
        client = SectorClient()
        if vmid := await client.get_vmid(id=self.payload.id, appliance="conduit"):
            return await self.succeed(f"Conduit for Sector {self.payload.id} already exists: {vmid}")
    
    async def provision(self) -> None:
        client = SectorClient()
        proxmox = Proxmox()
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_params(id=self.payload.id, vmid=vmid, appliance="conduit")
        
        await asyncio.gather(
            self.log(f"Creating Sector Conduit {vmid} with params: {self._redact_params(params=params)}"),
            proxmox.create_instance(instance_type="lxc", params=params),
        )
        
        await asyncio.gather(
            self.log("Setting Conduit VMID and starting Conduit"),
            client.set_vmid(id=self.payload.id, vmid=vmid, appliance="conduit"),
            proxmox.start(vmid=vmid),
        )
        
        await self.succeed(f"Created Conduit for Sector {self.payload.id}")
    
    async def configure(self) -> None:
        proxmox = Proxmox()
        sector = await SectorClient().get(id=self.payload.id)
        
        prefix = f"conduit-{sector.config.id}"
        commands = [
            f"etcdctl put {prefix}/http/middlewares/http-redirect/redirectscheme/scheme 'https'",
            f"etcdctl put {prefix}/http/middlewares/http-redirect/redirectscheme/port 443",
            f"etcdctl put {prefix}/http/middlewares/http-redirect/redirectscheme/permanent 'true'",
        ]
        
        etcd_member = await ETCDClient().get_random_member()
        async with await proxmox.create_connection() as connection:
            await asyncio.gather(
                self.log(f"Using VMID {etcd_member.vmid} to configure default HTTP to HTTPS redirect middleware"),
                connection.lxc_execute_script(
                    vmid=etcd_member.vmid,
                    content="\n".join(commands),
                )
            )
    
    async def on_succeed(self) -> None:
        """Update sector in frontend."""
        await self.emit_reflex_events(OrbitLabState.cache_clear("sectors"))


class SectorConduitUpdateV1(Workflow):
    """Workflow for updating a Sector Conduit (Traefik)."""
    
    TYPE: str = "sector.conduit.update"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[SectorPayload] = SectorPayload
    payload: SectorPayload
    
    async def validate(self) -> None:
        """Validate if pool does not exist."""
        client = SectorClient()
        if not await client.get_vmid(id=self.payload.id, appliance="conduit"):
            return await self.fail(f"Conduit for Sector {self.payload.id} does not exist.")
        
        infra = await ClusterClient().get_infra_appliances()
        if infra.version == await client.get_version(id=self.payload.id, appliance="conduit"):
            return await self.succeed(f"Sector {self.payload.id} Conduit aleady on version v{infra.version}")
        
        await SectorClient().set_sector_status(id=self.payload.id, status=SectorStatus.UPDATING)
        await self.emit_reflex_events(OrbitLabState.cache_clear("sectors"))
    
    async def provision(self) -> None:
        client = SectorClient()
        proxmox = Proxmox()
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_params(id=self.payload.id, vmid=vmid, appliance="conduit")
        
        await asyncio.gather(
            self.log(f"Creating new Sector Conduit {vmid} with params: {self._redact_params(params=params)}"),
            proxmox.create_instance(instance_type="lxc", params=params),
        )
        
        await asyncio.gather(
            self.log(f"Starting new Conduit {vmid} with 30 second warmup..."),
            proxmox.start(vmid=vmid),
            asyncio.sleep(30),
        )
        
        async with await proxmox.create_connection() as connection:
            await connection.lxc_execute_script(vmid=vmid, content="systemctl is-active --quiet conduit || exit 1")
        
        old_vmid = await client.get_vmid(id=self.payload.id, appliance="conduit")
        infra = await ClusterClient().get_infra_appliances()
        await asyncio.gather(
            self.log(f"Terminating old Conduit {old_vmid} and setting new VMID {vmid}"),
            proxmox.terminate(vmid=old_vmid),
            client.set_vmid(id=self.payload.id, appliance="conduit", vmid=vmid),
            client.set_version(id=self.payload.id, appliance="conduit", version=infra.version),
        )
        
        await self.succeed(f"Conduit Updated to v{infra.version}")
    
    async def on_succeed(self) -> None:
        """Update sector in frontend."""
        await SectorClient().set_sector_status(id=self.payload.id, status=SectorStatus.AVAILABLE)
        await self.emit_reflex_events(OrbitLabState.cache_clear("sectors"))


class SectorWardLinkCreateV1(Workflow):
    """Workflow for creating a Sector WardLink (WireGuard)."""
    
    TYPE: str = "sector.wardlink.create"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[SectorPayload] = SectorPayload
    payload: SectorPayload
    
    async def validate(self) -> None:
        """Validate if pool does not exist."""
        client = SectorClient()
        if vmid := await client.get_vmid(id=self.payload.id, appliance="wardlink"):
            return await self.succeed(f"WardLink for Sector {self.payload.id} already exists: {vmid}")
        
        await SectorClient().set_status(id=self.payload.id, appliance="wardlink", status=str(WardLinkStatus.PENDING))
        await self.emit_reflex_events(OrbitLabState.cache_clear("sectors"))
    
    async def provision(self) -> None:
        client = SectorClient()
        proxmox = Proxmox()
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_params(id=self.payload.id, vmid=vmid, appliance="wardlink")
        
        await asyncio.gather(
            self.log(f"Creating Sector WardLink {vmid} with params: {self._redact_params(params=params)}"),
            proxmox.create_instance(instance_type="lxc", params=params),
        )
        
        wardlink_cidr = await client.get_wardlink_cidr(id=self.payload.id)
        address = IPv4Interface(f"{wardlink_cidr.network_address + 1}/{wardlink_cidr.prefixlen}")
        secret = await SecretsClient().create_wardlink_keypair(sector=self.payload.id, name="server")
        key_pairs: WardLinkKeyPair = json.loads(secret.secret_string.get_secret_value())
        commands = [
            f"etcdctl put wardlink/{self.payload.id}/interface/private-key '{key_pairs['private']}'",
            f"etcdctl put wardlink/{self.payload.id}/interface/address '{address}'",
        ]
        
        etcd_member = await ETCDClient().get_random_member()
        async with await proxmox.create_connection() as connection:
            await asyncio.gather(
                self.log(f"Setting WardLink VMID and adding config via ETCD {etcd_member}"),
                client.set_vmid(id=self.payload.id, vmid=vmid, appliance="wardlink"),
                connection.lxc_execute_script(vmid=etcd_member.vmid, content="\n".join(commands))
            )
        
        infra = await ClusterClient().get_infra_appliances()
        await asyncio.gather(
                self.log(f"Starting WardLink v{infra.version} in Sector {self.payload.id}"),
                proxmox.start(vmid=vmid),
                client.set_version(id=self.payload.id, version=infra.version, appliance="wardlink"),
            )
        
        await self.succeed(f"Created WardLink for Sector {self.payload.id}")
    
    async def on_succeed(self) -> None:
        """Update sector in frontend."""
        await SectorClient().set_status(id=self.payload.id, appliance="wardlink", status=str(WardLinkStatus.RUNNING))
        await self.emit_reflex_events(OrbitLabState.cache_clear("sectors"))


class SectorGatewayUpdateV1(Workflow):
    """Workflow for updating a Sector Gateway."""
    
    TYPE: str = "sector.gateway.update"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[SectorPayload] = SectorPayload
    payload: SectorPayload
    
    async def validate(self) -> None:
        """Validate if pool does not exist."""
        client = SectorClient()
        if not await client.get_vmid(id=self.payload.id, appliance="gateway"):
            return await self.fail(f"Conduit for Sector {self.payload.id} does not exist.")
        
        infra = await ClusterClient().get_infra_appliances()
        if infra.version == await client.get_version(id=self.payload.id, appliance="gateway"):
            return await self.succeed(f"Sector {self.payload.id} Gateway aleady on version v{infra.version}")
        
        await SectorClient().set_sector_status(id=self.payload.id, status=SectorStatus.UPDATING)
        await self.emit_reflex_events(OrbitLabState.cache_clear("sectors"))
    
    async def provision(self) -> None:
        client = SectorClient()
        proxmox = Proxmox()
        vmid = await proxmox.get_next_vmid()
        params = await client.generate_params(id=self.payload.id, vmid=vmid, appliance="gateway")
        
        await asyncio.gather(
            self.log(f"Creating new Sector Gateway {vmid} with params: {self._redact_params(params=params)}"),
            proxmox.create_instance(instance_type="lxc", params=params),
        )
        
        await asyncio.gather(
            self.log(f"Starting new Gateway {vmid} with 30 second warmup..."),
            proxmox.start(vmid=vmid),
            asyncio.sleep(30),
        )
        
        commands = [
            "systemctl is-active --quiet nftables || exit 1",
            "systemctl is-active --quiet frr || exit 1",
            "systemctl is-active --quiet dnsmasq || exit 1",
            "systemctl is-active --quiet coredns || exit 1"
        ]
        async with await proxmox.create_connection() as connection:
            await connection.lxc_execute_script(vmid=vmid, content="\n".join(commands))
            
        await self.log(f"New Gateway {vmid} healthy.")
        old_vmid = await client.get_vmid(id=self.payload.id, appliance="gateway")
        infra = await ClusterClient().get_infra_appliances()
        await asyncio.gather(
            self.log(f"Terminating old Gateway {old_vmid} and setting new VMID {vmid}"),
            proxmox.terminate(vmid=old_vmid),
            client.set_vmid(id=self.payload.id, appliance="gateway", vmid=vmid),
            client.set_version(id=self.payload.id, appliance="gateway", version=infra.version),
        )
        
        await self.succeed(f"Sector {self.payload.id} Gateway Updated to v{infra.version}")
    
    async def on_succeed(self) -> None:
        """Update sector in frontend."""
        await SectorClient().set_sector_status(id=self.payload.id, status=SectorStatus.AVAILABLE)
        await self.emit_reflex_events(OrbitLabState.cache_clear("sectors"))


class ConduitSyncPayload(SectorPayload):
    removed_domains: list[str] = Field(default_factory=list)


class SectorConduitSyncV1(Workflow):
    """Workflow for syncing a Sector Conduit's configuration."""
    
    TYPE: str = "sector.conduit.sync"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[ConduitSyncPayload] = ConduitSyncPayload
    payload: ConduitSyncPayload
    
    def _yaml_format_domain(self, domain: str) -> str:
        return domain.replace(".", "-")
    
    async def validate(self) -> None:
        """Validate if pool does not exist."""
        client = SectorClient()
        if not await client.get_vmid(id=self.payload.id, appliance="conduit"):
            return await self.fail(f"Conduit for Sector {self.payload.id} does not exist.")
    
    async def provision(self) -> None:
        client = SectorClient()
        cluster = ClusterClient()
        secrets = SecretsClient()
        proxmox = Proxmox()
        
        sector = await client.get(id=self.payload.id)
        
        prefix = f"conduit-{sector.config.id}"
        commands = [
            f"etcdctl del --prefix {prefix}/http/routers/cert-{self._yaml_format_domain(domain=domain)}"
            for domain in self.payload.removed_domains
        ]
        commands.append(f"etcdctl del --prefix {prefix}/resolvers")
        for domain_config in sector.config.domains:
            domain_provider = await cluster.get_domain_provider(name=domain_config.domain_provider)
            credentials = await secrets.get_service_secret(service_name="domain_provider", service_id=domain_provider.name)
            formatted_domain = self._yaml_format_domain(domain=domain_config.domain)
            resolver = f"{domain_provider.provider}-{formatted_domain}"
            commands.extend([
                f"etcdctl put {prefix}/resolvers/{resolver}/acme/email '{domain_provider.email}'",
                f"etcdctl put {prefix}/resolvers/{resolver}/acme/storage '/etc/traefik/{resolver}-acme.json'",
                f"etcdctl put {prefix}/resolvers/{resolver}/acme/provider '{domain_provider.provider}'",
                f"etcdctl put {prefix}/resolvers/{resolver}/acme/credentials '{credentials}'",
                f"etcdctl put {prefix}/http/routers/cert-{formatted_domain}/rule 'Host(`_cert-issuer.{domain_config.domain}`)'",
                f"etcdctl put {prefix}/http/routers/cert-{formatted_domain}/service 'noop@internal'",
                f"etcdctl put {prefix}/http/routers/cert-{formatted_domain}/tls/certResolver '{resolver}'",
                f"etcdctl put {prefix}/http/routers/cert-{formatted_domain}/tls/certResolver '{resolver}'",
            ])
            await self.log(f"Generated sync commands for '{domain_config.domain}' with provider '{domain_config.domain_provider}'")
        
        etcd_member = await ETCDClient().get_random_member()
        async with await proxmox.create_connection() as connection:
            await asyncio.gather(
                self.log(f"Using VMID {etcd_member.vmid} to create {self.payload.id}"),
                connection.lxc_execute_script(
                    vmid=etcd_member.vmid,
                    content="\n".join(commands),
                )
            )
            await asyncio.gather(
                self.log(f"Restarting Sector {self.payload.id} Conduit"),
                connection.lxc_execute_script(
                    vmid=sector.state.conduit_vmid,
                    content="systemctl restart conduit",
                )
            )
        
        await self.succeed("Conduit Synced")
    
    async def on_succeed(self) -> None:
        """Update sector in frontend."""
        await self.emit_reflex_events(OrbitLabState.cache_clear("sectors"))


class DeleteSectorV1(Workflow):
    """Delete a Sector."""

    TYPE: str = "sector.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[SectorPayload] = SectorPayload
    payload: SectorPayload

    async def validate(self) -> None:
        """Validate the sector exists."""
        if not await SectorClient().sector_exists(id=self.payload.id):
            return await self.succeed(f"Sector {self.payload.id} doesn't exist or already deleted.")
        await SectorClient().set_sector_status(id=self.payload.id, status=SectorStatus.DELETING)
        await self.emit_reflex_events(OrbitLabState.cache_clear("sectors"))

    async def provision(self) -> None:
        """Delete the sector and appliance."""
        proxmox = Proxmox()
        sector = await SectorClient().get(id=self.payload.id)
        
        if sector.state.gateway_vmid:
            await asyncio.gather(
                self.log(f"Terminating sector gateway {sector.state.gateway_vmid}"),
                proxmox.terminate(vmid=sector.state.gateway_vmid),
            )
            
        subnet_id = str(sector.config.cidr_block).replace("/", "-")
        await asyncio.gather(
            self.log(f"Deleting sector subnet {subnet_id}"),
            proxmox.delete(
                path=f"/cluster/sdn/vnets/{sector.config.bridge}/subnets/{sector.config.bridge}-{subnet_id}",
                model=None,
            ),
        )
        
        await asyncio.gather(
            self.log(f"Deleting sector vnet {sector.config.bridge}"),
            proxmox.delete(path=f"/cluster/sdn/vnets/{sector.config.bridge}", model=None),
        )
        
        await asyncio.gather(
            self.log(f"Deleting sector zone {sector.config.bridge}"),
            proxmox.delete(path=f"/cluster/sdn/zones/{sector.config.bridge}", model=None),
        )
        
        await asyncio.gather(
            self.log("Applying SDN deletion changes..."),
            proxmox.set(path="/cluster/sdn"),
            SectorClient().delete(id=self.payload.id),
            DNSClient().delete_sector_zone(sector_id=self.payload.id),
        )

        await self.succeed(f"Sector {self.payload.id} deleted.")

    async def on_succeed(self) -> None:
        """Delete the state from Redis."""
        await self.emit_reflex_events(OrbitLabState.cache_clear("sectors"))

    async def on_failure(self) -> None:
        """Actions to perform on workflow failure."""
        await self.emit_reflex_events(OrbitLabState.cache_clear("sectors"))
