"""Durable first-run bootstrap for an OrbitLab installation."""

from __future__ import annotations

import asyncio
from ipaddress import IPv4Network
from typing import get_args

from orbitlab.data_types import BackplaneStatus, ETCDStatus, OrbitLabApplianceType
from orbitlab.proxmox import Proxmox, ProxmoxAdapter
from orbitlab.redis import models
from orbitlab.redis.clients import BackplaneClient, ClusterClient, DNSClient, ETCDClient
from orbitlab.redis.models import ARecord, InfraAppliance, InfraAppliances, NodeConfig, SRVRecord

from .base import Workflow, WorkflowPayload


class BootstrapPayload(WorkflowPayload):
    """Structured, serializable bootstrap input submitted by the setup page."""

    backplane_cidr: str
    defaults: models.Defaults
    acknowledged: bool = False
    zone_tag: int = 0
    vnet_tag: int = 0


class BootstrapInitializeV1(Workflow):
    """Discover PVE, establish OrbitLab infrastructure, and record its identity."""

    TYPE = "bootstrap.initialize"
    SCHEMA = "v1"
    PAYLOAD_TYPE = BootstrapPayload
    payload: BootstrapPayload

    async def validate(self) -> None:
        """Discover PVE and commit the operator's immutable installation inputs."""
        if not self.payload.acknowledged:
            return await self.fail("Acknowledge the Proxmox networking changes before initialization.")
        missing = self.payload.defaults.valid()
        if missing:
            return await self.fail(f"The required default '{missing}' is not configured.")

        cidr = IPv4Network(self.payload.backplane_cidr, strict=True)
        if not 8 <= cidr.prefixlen <= 24:
            return await self.fail("Backplane CIDR must be between /8 and /24.")

        proxmox = Proxmox()
        cluster = ClusterClient()
        backplane_client = BackplaneClient()
        if await cluster.is_initialized():
            return await self.succeed("OrbitLab is already initialized.")

        nodes = await proxmox.list_nodes()
        if not nodes:
            return await self.fail("No Proxmox nodes were discovered.")
        lan_network = (await proxmox.get_vmbr0_for_node(nodes[0].name)).cidr.network
        if cidr.overlaps(lan_network):
            return await self.fail(f"Backplane CIDR {cidr} overlaps vmbr0 network {lan_network}.")

        if await backplane_client.exists():
            backplane = await backplane_client.get()
            if backplane.config.cidr_block != cidr:
                return await self.fail(
                    f"Backplane is already configured as {backplane.config.cidr_block}; it cannot be changed in place."
                )
            self.payload.zone_tag = backplane.config.zone_tag
            self.payload.vnet_tag = backplane.config.vnet_tag
        else:
            controllers = await proxmox.list_controllers()
            if existing := controllers.get_evpn_controller():
                return await self.fail(
                    f"PVE already has EVPN controller '{existing.controller}'. OrbitLab will not replace it."
                )
            await backplane_client.add_used_vlan_tags((await proxmox.list_vnets()).get_all_tags())
            zone_tag = await backplane_client.get_next_vlan_tag(start=10, end=99)
            vnet_tag = await backplane_client.get_next_vlan_tag(start=100, end=999)
            if zone_tag is None or vnet_tag is None:
                return await self.fail("No suitable VLAN tags remain for the OrbitLab Backplane.")
            self.payload.zone_tag = zone_tag
            self.payload.vnet_tag = vnet_tag

        for node in nodes:
            await cluster.set_node(
                NodeConfig(
                    name=node.name,
                    address=node.ip,
                    proxmox_version=await proxmox.get_node_proxmox_version(node.name),
                )
            )
            await cluster.set_node_online(node.name, node.online)
        await asyncio.gather(
            cluster.set_lan_network(lan_network),
            cluster.set_defaults(self.payload.defaults),
        )
        await self.log(f"Validated {len(nodes)} Proxmox node(s), LAN {lan_network}, and Backplane {cidr}.")

    async def provision(self) -> None:
        """Create the cluster-wide PVE SDN primitives in one serialized operation."""
        backplane_client = BackplaneClient()
        if await backplane_client.exists():
            await self.log("Backplane configuration already exists; retaining it for the retry.")
            return

        cluster = ClusterClient()
        nodes = await cluster.list_nodes()
        backplane = models.BackplaneConfig(
            cidr_block=IPv4Network(self.payload.backplane_cidr, strict=True),
            controller=models.Controller(peers=[node.config.address for node in nodes]),
            zone_tag=self.payload.zone_tag,
            vnet_tag=self.payload.vnet_tag,
            mtu=(await Proxmox().get_mtu()) - 50,
            exit_nodes=[node.config.name for node in nodes],
        )
        await backplane_client.set(backplane)
        proxmox = Proxmox()
        lan_network = await cluster.get_lan_network()

        async def apply_sdn() -> None:
            await proxmox.create_backplane(backplane)
            await proxmox.create_fabric(lan_network)
            for node in nodes:
                await proxmox.add_node_to_fabric(node.config.name, node.config.address)
            await proxmox.set(path="/cluster/sdn")

        await ProxmoxAdapter(proxmox).apply_sdn(apply_sdn)
        await self.log("Created and applied Backplane EVPN, VNet, and fabric configuration.")

    async def configure(self) -> None:
        """Download appliance inputs and create the Backplane controller exactly once."""
        await self._download_infrastructure()
        backplane = BackplaneClient()
        if await backplane.backplane_controller_exists():
            await self.log("Backplane controller already has a committed VMID; retaining it for the retry.")
            return

        proxmox = Proxmox()
        defaults = await ClusterClient().get_defaults()
        guest = await ProxmoxAdapter(proxmox).create_managed_guest(
            resource_id="backplane:controller",
            instance_type="lxc",
            node=defaults.node,
            parameters=backplane.generate_backplane_params,
        )
        await proxmox.attach_redis_socket_file(vmid=guest.vmid)
        await proxmox.start(vmid=guest.vmid)
        infra = await ClusterClient().get_infra_appliances()
        await asyncio.gather(
            backplane.set_vmid(guest.vmid),
            backplane.set_appliance_version(infra.version),
        )
        await self.log(f"Created Backplane controller VMID {guest.vmid}.")

    async def finalize(self) -> None:
        """Create ETCD, publish DNS records, and wait with bounded readiness probes."""
        etcd = ETCDClient()
        if not await etcd.list_members():
            await self._create_etcd_members(etcd)
        members = await etcd.list_members()
        await asyncio.gather(
            *(Proxmox().wait_for_lxc_services(member.vmid, ["/usr/bin/etcd-mgr health-check"]) for member in members),
        )
        infra = await ClusterClient().get_infra_appliances()
        await asyncio.gather(
            etcd.set_version(infra.version),
            etcd.set_status(ETCDStatus.AVAILABLE),
            BackplaneClient().set_status(BackplaneStatus.AVAILABLE),
        )
        await self.log(f"ETCD cluster with {len(members)} members is healthy.")

    async def on_succeed(self) -> None:
        """Expose the lab only after its baseline infrastructure is available."""
        await ClusterClient().set_initialized()

    async def _download_infrastructure(self) -> None:
        """Fetch the selected Appliances branch into the configured PVE stores."""
        cluster = ClusterClient()
        proxmox = Proxmox()
        branch = await cluster.get_appliances_branch()
        latest = await proxmox.get_infrastructure_appliances(branch)
        try:
            installed = await cluster.get_infra_appliances()
        except Exception:  # The first initialization has no existing manifest.
            installed = InfraAppliances.empty()
        if installed.version == latest.version and installed.appliances:
            await self.log(f"Infrastructure appliance release {latest.version} is already available.")
            return

        defaults = await cluster.get_defaults()
        downloaded = InfraAppliances(appliances={}, version=latest.version)
        for appliance_type in get_args(OrbitLabApplianceType.__value__):
            appliance = latest.get_appliance(appliance_type=appliance_type)
            storage, content = (defaults.imports, "import") if appliance.filename.endswith(".qcow2") else (defaults.vztmpl, "vztmpl")
            checksum_algorithm, checksum = appliance.digest.split(":", maxsplit=1)
            volume_id = await proxmox.download_infrastructure_appliance(
                storage=storage,
                node=defaults.node,
                params={
                    "content": content,
                    "url": appliance.browser_download_url,
                    "filename": appliance.filename,
                    "checksum": checksum,
                    "checksum-algorithm": checksum_algorithm,
                },
            )
            downloaded.add(appliance_type, InfraAppliance(node=defaults.node, volume_id=volume_id))
            await self.log(f"Downloaded {appliance_type} release {latest.version} to {volume_id}.")
        await cluster.set_infra_appliances(downloaded)

    async def _create_etcd_members(self, etcd: ETCDClient) -> None:
        """Create members first, then commit their PVE-assigned VMIDs and DNS records."""
        cluster = ClusterClient()
        defaults = await cluster.get_defaults()
        proxmox = Proxmox()
        await proxmox.create_pool(pool_id="orbitlab-etcd", alias="OrbitLab ETCD")
        dns = DNSClient()
        adapter = ProxmoxAdapter(proxmox)
        members: list[models.ETCDMember] = []
        for _ in range(3):
            prepared: dict[str, models.ETCDMember] = {}

            async def parameters(vmid: int) -> dict:
                member, params = await etcd.generate_create_params(vmid)
                prepared["member"] = member
                return params

            guest = await adapter.create_managed_guest(
                resource_id=f"etcd:bootstrap:{len(members)}",
                instance_type="lxc",
                node=defaults.node,
                parameters=parameters,
            )
            member = prepared["member"]
            if member.vmid != guest.vmid:
                raise RuntimeError("ETCD member VMID did not match the PVE create result.")
            await etcd.add_member(member)
            await proxmox.start(vmid=member.vmid)
            members.append(member)

        access_records = [ARecord(ip=member.address.ip) for member in members]
        await asyncio.gather(
            *(dns.add_backplane_a_records(member.name, ARecord(ip=member.address.ip)) for member in members),
            dns.add_backplane_a_records("etcd", *access_records),
            dns.add_backplane_srv_records("etcd-server", "tcp", *(SRVRecord(target=member.name, port=2380) for member in members)),
            dns.add_backplane_srv_records("etcd-client", "tcp", *(SRVRecord(target=member.name, port=2379) for member in members)),
        )
