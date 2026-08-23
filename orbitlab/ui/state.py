"""UI-facing service composition, read models, and operator commands.

The NiceGUI layer talks to this module rather than to Redis models directly.
It keeps browser views simple, makes displayed data intentional, and preserves
a single shared asynchronous Redis connection for the UI process.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from ipaddress import IPv4Network
import os
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis

from orbitlab.proxmox import Proxmox
from orbitlab.redis import models
from orbitlab.redis.clients import (
    ApplianceClient,
    AutoscalingClient,
    BackplaneClient,
    ClusterClient,
    ConduitClient,
    DataCoreClient,
    DockFSClient,
    ImagesClient,
    InstanceClient,
    LogsClient,
    PKIClient,
    SSHKeyClient,
    SecretsClient,
    SectorClient,
)
from orbitlab.worker.events import WorkflowEvent
from orbitlab.worker.jobs import Job, JobStore
from orbitlab.worker.worker import Worker


def _redis_connection() -> Redis:
    """Create the one async Redis connection used by the UI process."""
    if redis_url := os.environ.get("ORBITLAB_REDIS_URL"):
        return Redis.from_url(redis_url)
    return Redis(db=10)


def _bind_redis(client: Any, redis: Redis) -> Any:
    """Bind a focused Redis client to the application's shared connection."""
    client.__dict__["client"] = redis
    return client


@dataclass(frozen=True, slots=True)
class SummaryCard:
    """A compact, display-only lab health summary."""

    title: str
    value: str
    detail: str
    status: str
    path: str


@dataclass(frozen=True, slots=True)
class AttentionItem:
    """An operator action or health concern shown on the overview page."""

    title: str
    detail: str
    severity: str
    path: str


@dataclass(frozen=True, slots=True)
class DetailSection:
    """A named collection of safe, readable resource facts."""

    title: str
    values: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ResourceDetail:
    """The display contract for a resource-specific NiceGUI page."""

    title: str
    subtitle: str
    status: str
    sections: tuple[DetailSection, ...]
    actions: tuple[str, ...] = field(default_factory=tuple)


class Queries:
    """Read facade used by NiceGUI pages; views never read Redis directly."""

    def __init__(self, clients: Clients) -> None:
        self._clients = clients

    async def overview(self) -> tuple[list[SummaryCard], list[AttentionItem]]:
        """Return the operator-focused dashboard snapshot."""
        nodes, sectors, instances, datacores, dockfs, endpoints, drift = await asyncio.gather(
            *self._clients.gather_inventory(), self.drift(),
        )
        online_nodes = sum(node.state.online for node in nodes)
        running_instances = sum(str(item.state.status).lower() == "running" for item in instances)
        unhealthy_datacores = [item for item in datacores if "available" not in str(item.state.status).lower()]
        unhealthy_dockfs = [item for item in dockfs if "available" not in str(item.state.status).lower()]
        attention: list[AttentionItem] = []
        attention.extend(
            AttentionItem(node.config.name, "Proxmox node is offline", "critical", "/nodes")
            for node in nodes if not node.state.online
        )
        attention.extend(
            AttentionItem(item.config.name, f"DataCore is {item.state.status}", "warning", "/datacore")
            for item in unhealthy_datacores
        )
        attention.extend(
            AttentionItem(item.config.name, f"DockFS is {item.state.status}", "warning", "/dock-fs")
            for item in unhealthy_dockfs
        )
        attention.extend(AttentionItem(resource_id, detail, "warning", "/compute") for resource_id, detail in drift)
        cards = [
            SummaryCard("Nodes", f"{online_nodes}/{len(nodes)} online", "Proxmox hosts", "healthy" if online_nodes == len(nodes) else "warning", "/nodes"),
            SummaryCard("Compute", f"{running_instances}/{len(instances)} running", "Managed VMs and LXCs", "healthy", "/compute"),
            SummaryCard("Sectors", str(len(sectors)), "Isolated networks", "healthy", "/sectors"),
            SummaryCard("Data services", str(len(datacores) + len(dockfs)), "DataCore and DockFS", "warning" if unhealthy_datacores or unhealthy_dockfs else "healthy", "/datacore"),
            SummaryCard("Ingress", str(len(endpoints)), "Published Conduit endpoints", "healthy", "/conduit"),
        ]
        return cards, attention

    async def drift(self) -> list[tuple[str, str]]:
        """Return flag-only desired-versus-observed discrepancies."""
        values = await self._clients.redis.hgetall("ol:drift")
        return [(self._decode(resource_id), self._decode(detail)) for resource_id, detail in values.items()]

    async def rows(self, resource: str) -> list[dict[str, str]]:
        """Return concise inventory rows for a collection page."""
        loaders: dict[str, Callable[[], Awaitable[Any]]] = {
            "nodes": self._clients.nodes.list_nodes,
            "compute": self._clients.instances.list_instances,
            "sectors": self._clients.sectors.list_sectors,
            "datacore": self._clients.datacore.list_datacores,
            "dock-fs": self._clients.dockfs.list_dockfs_clusters,
            "conduit": self._clients.conduit.list_endpoints,
            "conduit-pools": self._clients.conduit.list_pools,
            "appliances": self._template_rows(self._clients.appliances.list_appliances),
            "images": self._template_rows(self._clients.images.list_images),
            "secrets": self._clients.secrets.list_secrets,
            "root-certificates": self._clients.pki.list_root_certificates,
            "intermediate-certificates": self._clients.pki.list_intermediate_certificates,
            "leaf-certificates": self._clients.pki.list_leaf_certificates,
            "ssh-keys": self._clients.ssh_keys.list_named_key_pairs,
        }
        values = await loaders[resource]()
        return [self._resource_row(resource, value) for value in values]

    async def detail(self, resource: str, resource_id: str) -> ResourceDetail:
        """Return a safe, resource-specific detail contract."""
        return self._resource_detail(resource, await self._resource(resource, resource_id))

    async def jobs(self) -> list[dict[str, str]]:
        """Return compact durable operation rows for the Activity page."""
        return [
            {"id": job.id, "name": job.name, "status": job.status, "location": job.created_at, "detail": job.id, "path": f"/activity/{job.id}"}
            for job in await JobStore(self._clients.redis).list_recent()
        ]

    async def job(self, job_id: str) -> ResourceDetail:
        """Return durable job state as an inspection page."""
        job = await JobStore(self._clients.redis).get(job_id)
        return ResourceDetail(
            title=job.name,
            subtitle=f"Job {job.id}",
            status=job.status,
            sections=(
                DetailSection("Operation", (("Status", job.status), ("Created", job.created_at), ("Job ID", job.id))),
            ),
        )

    async def logs(self, source: str) -> list[str]:
        """Read a bounded log snapshot on the operator's explicit request."""
        _last_id, values = await (
            self._clients.logs.get_workflow_logs() if source == "workflow" else self._clients.logs.get_system_logs()
        )
        return values

    async def options(self) -> dict[str, list[str]]:
        """Return small select lists used by explicit creation dialogs."""
        nodes, sectors, appliances, images = await asyncio.gather(
            self._clients.nodes.list_nodes(),
            self._clients.sectors.list_sectors(),
            self._template_rows(self._clients.appliances.list_appliances)(),
            self._template_rows(self._clients.images.list_images)(),
        )
        return {
            "nodes": [node.config.name for node in nodes],
            "sectors": [sector.config.id for sector in sectors],
            "appliances": [item.config.id for item in appliances],
            "images": [item.config.id for item in images],
        }

    @staticmethod
    def _decode(value: bytes | str) -> str:
        return value.decode() if isinstance(value, bytes) else value

    @staticmethod
    def _template_rows(loader: Callable[[str], Awaitable[Any]]) -> Callable[[], Awaitable[list[Any]]]:
        async def load() -> list[Any]:
            base, custom = await asyncio.gather(loader("base"), loader("custom"))
            return [*base, *custom]

        return load

    async def _resource(self, resource: str, resource_id: str) -> Any:
        getters: dict[str, Callable[[str], Awaitable[Any]]] = {
            "sectors": self._clients.sectors.get,
            "compute": self._clients.instances.get_instance,
            "datacore": self._clients.datacore.get_datacore,
            "dock-fs": self._clients.dockfs.get_dockfs,
            "conduit": self._clients.conduit.get_endpoint,
            "conduit-pools": self._clients.conduit.get_pool,
            "secrets": self._clients.secrets.get,
            "root-certificates": self._clients.pki.get_root_certificate,
            "intermediate-certificates": self._clients.pki.get_intermediate_certificate,
            "leaf-certificates": self._clients.pki.get_leaf_certificate,
            "ssh-keys": self._clients.ssh_keys.get_key_pair,
        }
        if resource == "nodes":
            return await self._clients.nodes.get_node(resource_id)
        if resource in {"appliances", "images"}:
            client = self._clients.appliances if resource == "appliances" else self._clients.images
            for kind in ("base", "custom"):
                try:
                    if resource == "appliances":
                        return await client.get_appliance(kind, resource_id)
                    return await client.get_image(kind, resource_id)
                except Exception:  # Client-specific not-found exceptions are intentionally hidden from the view.
                    continue
            raise ValueError(f"{resource.rstrip('s').title()} '{resource_id}' was not found.")
        return await getters[resource](resource_id)

    @staticmethod
    def _resource_row(resource: str, value: Any) -> dict[str, str]:
        if resource == "nodes":
            return {"id": value.config.name, "name": value.config.name, "status": "Maintenance" if value.state.maintenance_mode else "Online" if value.state.online else "Offline", "location": str(value.config.address), "detail": value.config.proxmox_version, "path": f"/nodes/{value.config.name}"}
        if resource == "compute":
            return {"id": value.config.id, "name": value.config.name, "status": str(value.state.status), "location": value.config.node, "detail": f"{value.config.type.upper()} · {value.config.sector_name}", "path": f"/compute/{value.config.id}"}
        if resource == "sectors":
            return {"id": value.config.id, "name": value.config.alias, "status": str(value.state.gateway_status), "location": str(value.config.cidr_block), "detail": f"{value.config.id} · VLAN {value.config.tag}", "path": f"/sectors/{value.config.id}"}
        if resource == "datacore":
            return {"id": value.config.id, "name": value.config.name, "status": str(value.state.status), "location": value.config.sector_name, "detail": f"{len(value.state.nodes.root)} members · {value.config.capacity_gb} GiB", "path": f"/datacore/{value.config.id}"}
        if resource == "dock-fs":
            active = value.state.active.name if value.state.active else "No active member"
            return {"id": value.config.id, "name": value.config.name, "status": str(value.state.status), "location": value.config.sector_name, "detail": f"{active} · {value.config.capacity_gb} GiB", "path": f"/dock-fs/{value.config.id}"}
        if resource == "conduit":
            listener = str(value.state.listener_address) if value.state.listener_address else "Not assigned"
            return {"id": value.config.id, "name": value.config.name, "status": "Configured", "location": value.config.sector_name, "detail": f"{value.config.domain} · {listener}", "path": f"/conduit/{value.config.id}"}
        if resource == "conduit-pools":
            return {"id": value.config.id, "name": value.config.name, "status": value.state.health, "location": value.config.sector_name, "detail": f"{len(value.config.targets)} targets · {value.config.port}", "path": f"/conduit/pools/{value.config.id}"}
        if resource in {"appliances", "images"}:
            template_type = "Custom" if hasattr(value.config, "name") else "Base"
            name = getattr(value.config, "name", value.config.id)
            status = getattr(value.state, "workflow_status", "Available" if value.state.volume_id else "Not downloaded")
            detail = getattr(value.state, "volume_id", "") or getattr(value.config, "description", "") or "No volume has been produced yet"
            return {"id": value.config.id, "name": name, "status": str(status), "location": template_type, "detail": detail, "path": f"/{resource}/{value.config.id}"}
        if resource == "secrets":
            return {"id": value.name, "name": value.name, "status": f"Version {value.secret_version}", "location": value.created_at.isoformat(), "detail": value.description or "No description", "path": f"/secrets-pki/secrets/{value.name}"}
        if resource == "ssh-keys":
            key_name, key = value
            return {"id": key_name, "name": key_name, "status": str(key.key_type), "location": "SSH", "detail": key.fingerprint, "path": f"/secrets-pki/ssh-keys/{key_name}"}
        common_name = value.subject.common_name
        return {"id": common_name, "name": common_name, "status": value.status, "location": value.issuer, "detail": f"Expires {value.not_after.date().isoformat()}", "path": f"/secrets-pki/pki/{resource}/{common_name}"}

    @staticmethod
    def _resource_detail(resource: str, value: Any) -> ResourceDetail:
        def section(title: str, values: dict[str, Any]) -> DetailSection:
            return DetailSection(title, tuple((key, str(item) if item is not None else "—") for key, item in values.items()))

        if resource == "nodes":
            return ResourceDetail(value.config.name, str(value.config.address), "Online" if value.state.online else "Offline", (section("Host", {"Address": value.config.address, "Proxmox version": value.config.proxmox_version, "Maintenance mode": value.state.maintenance_mode}),))
        if resource == "compute":
            return ResourceDetail(value.config.name, value.config.id, str(value.state.status), (section("Runtime", {"VMID": value.state.vmid or "Not assigned", "Node": value.config.node, "Address": value.state.address}), section("Requested capacity", {"Type": value.config.type.upper(), "Cores": value.config.cores, "Memory": f"{value.config.memory} MiB", "Disk": f"{value.config.disk_size} GiB", "Sector": value.config.sector_name})), ("refresh-ip", "start", "reboot", "stop", "terminate", "proxmox"))
        if resource == "sectors":
            return ResourceDetail(value.config.alias, value.config.id, str(value.state.gateway_status), (section("Network", {"CIDR": value.config.cidr_block, "VLAN": value.config.tag, "Storage": value.config.storage, "DNS": value.config.dns_address}), section("Services", {"Gateway": value.state.gateway_status, "Conduit": value.state.conduit_status, "WardLink": value.state.wardlink_status, "Domains": ", ".join(domain.domain for domain in value.config.domains) or "None"})), ("create-conduit", "update-gateway", "delete"))
        if resource == "datacore":
            return ResourceDetail(value.config.name, value.config.id, str(value.state.status), (section("Service", {"Sector": value.config.sector_name, "Read/write VIP": value.config.rw_vip, "Read-only VIP": value.config.ro_vip, "Capacity": f"{value.config.capacity_gb} GiB"}), section("Members", {node.name: f"{node.role or 'pending'} · {'online' if node.online else 'offline'} · VMID {node.vmid}" for node in value.state.nodes.root})), ("delete",))
        if resource == "dock-fs":
            return ResourceDetail(value.config.name, value.config.id, str(value.state.status), (section("Service", {"Sector": value.config.sector_name, "VIP": value.config.vip, "Capacity": f"{value.config.capacity_gb} GiB", "Storage": value.config.storage}), section("Members", {"Active": value.state.active.name if value.state.active else "Not assigned", "Passive": value.state.passive.name if value.state.passive else "Not assigned"})), ("delete",))
        if resource == "conduit":
            return ResourceDetail(value.config.name, value.config.id, "Configured", (section("Endpoint", {"Domain": value.config.domain, "Type": value.config.type, "Port": value.config.port, "Listener": value.state.listener_address}), section("Routing", {"Pool": value.config.pool_name, "Sector": value.config.sector_name, "Rules": ", ".join(rule.to_rule() for rule in value.config.rules)})), ("delete",))
        if resource == "conduit-pools":
            return ResourceDetail(value.config.name, value.config.id, value.state.health, (section("Pool", {"Type": value.config.type, "Sector": value.config.sector_name, "Port": value.config.port, "Strategy": value.config.balance}), section("Targets", {target.instance_id: value.state.targets_health.get(target.instance_id, "unknown") for target in value.config.targets})), ("delete",))
        if resource == "secrets":
            return ResourceDetail(value.name, "Secret material is never shown in the UI.", f"Version {value.secret_version}", (section("Metadata", {"Description": value.description or "None", "Created": value.created_at, "Last rotation": value.last_rotation, "Previous versions": ", ".join(map(str, sorted(value.metadata.previous_versions))) or "None"}),), ("rotate", "rollback", "delete"))
        if resource == "ssh-keys":
            return ResourceDetail("SSH key", value.fingerprint, str(value.key_type), (section("Public key", {"Fingerprint": value.fingerprint, "Public key": value.public_key}),), ("delete",))
        if resource in {"appliances", "images"}:
            is_custom = hasattr(value.config, "name")
            source = getattr(value.config, "base_appliance_id", "") or getattr(value.config, "base_image_id", "")
            return ResourceDetail(
                getattr(value.config, "name", value.config.id),
                value.config.id,
                str(getattr(value.state, "workflow_status", "available" if value.state.volume_id else "not downloaded")),
                (
                    section("Template", {"Kind": "Custom" if is_custom else "Base", "Volume": value.state.volume_id or "Not available", "Source": source or getattr(value.config, "template", getattr(value.config, "filename", "")), "Node": value.config.node}),
                ),
                (("build" if is_custom else "download"), "delete"),
            )
        if resource in {"root-certificates", "intermediate-certificates", "leaf-certificates"}:
            extra = {"DNS names": ", ".join(value.san_dns), "IP addresses": ", ".join(value.san_ips)} if resource == "leaf-certificates" else {}
            if resource == "intermediate-certificates":
                extra["Domain constraint"] = value.domain_constraint
            return ResourceDetail(value.subject.common_name, value.issuer, value.status, (section("Certificate", {"Issuer": value.issuer, "Fingerprint": value.fingerprint, "Not before": value.not_before, "Expires": value.not_after, **extra}),), ("delete",))
        config = value.config
        return ResourceDetail(getattr(config, "name", config.id), config.id, "Configured", (section("Configuration", {"Identifier": config.id}),))


class Commands:
    """User-initiated commands validated before durable persistence."""

    def __init__(self, clients: Clients) -> None:
        self._clients = clients

    async def set_appliances_branch(self, branch: str) -> str:
        """Validate branch metadata remotely, then make it the selected source."""
        normalized = branch.strip()
        if not normalized:
            raise ValueError("Enter an Appliances branch name.")
        metadata = await Proxmox().get_infrastructure_appliances(normalized)
        await self._clients.cluster.set_appliances_branch(normalized)
        return f"Using Appliances branch '{normalized}' (release metadata {metadata.version})."

    async def enqueue(self, *, name: str, version: str = "v1", payload: dict[str, Any], idempotency_key: str | None = None) -> Job:
        """Validate a command against the registered workflow and queue it once."""
        workflow = Worker.registry.resolve(event=WorkflowEvent(name=name, version=version))
        if workflow is None:
            raise ValueError(f"Unsupported OrbitLab command: {name}@{version}")
        validated = workflow.PAYLOAD_TYPE.model_validate(payload)
        return await JobStore(self._clients.redis).enqueue(name=name, version=version, payload=validated.model_dump(mode="json"), idempotency_key=idempotency_key or str(uuid4()))

    async def initialize_orbitlab(
        self,
        *,
        backplane_cidr: str,
        node: str,
        vztmpl: str,
        imports: str,
        rootdir: str,
        images: str,
        snippets: str = "",
        iso: str = "",
        backup: str = "",
        acknowledged: bool,
    ) -> Job:
        """Validate structured setup input and queue the durable bootstrap worker."""
        defaults = models.Defaults(
            node=node.strip(),
            vztmpl=vztmpl.strip(),
            imports=imports.strip(),
            rootdir=rootdir.strip(),
            images=images.strip(),
            snippets=snippets.strip(),
            iso=iso.strip(),
            backup=backup.strip(),
        )
        if missing := defaults.valid():
            raise ValueError(f"Choose a value for '{missing}'.")
        if not acknowledged:
            raise ValueError("Confirm that OrbitLab may create and manage its PVE networking baseline.")
        return await self.enqueue(
            name="bootstrap.initialize",
            payload={
                "backplane_cidr": backplane_cidr.strip(),
                "defaults": defaults.model_dump(mode="json"),
                "acknowledged": acknowledged,
            },
        )

    async def create_secret(self, *, name: str, value: str, description: str) -> None:
        if not name.strip() or not value:
            raise ValueError("A secret name and value are required.")
        await self._clients.secrets.create(name.strip(), value, description.strip())

    async def create_compute(
        self,
        *,
        instance_type: str,
        name: str,
        source_id: str,
        node: str,
        storage: str,
        sector_id: str,
        disk_size: int,
        memory: int,
        cores: int,
        password: str,
        sockets: int = 1,
        swap: int = 512,
    ) -> Job:
        """Persist a validated compute manifest, then queue its creation once."""
        if not all((name.strip(), source_id.strip(), node.strip(), storage.strip(), sector_id.strip())):
            raise ValueError("Name, source, node, storage, and sector are required.")
        sector = await self._clients.sectors.get(sector_id)
        source = self._clients.appliances if instance_type == "lxc" else self._clients.images
        volume_id = await source.get_volume_id(source_id)
        if not volume_id:
            raise ValueError("The selected source has not produced a usable volume yet.")
        instance_id = await self._clients.instances.generate_instance_id()
        config = models.InstanceConfig.model_validate({
            "type": instance_type,
            "id": instance_id,
            "name": name.strip(),
            "base_id": source_id,
            "volume_id": volume_id,
            "storage": storage.strip(),
            "disk_size": disk_size,
            "sector": sector_id,
            "sector_name": sector.config.alias,
            "memory": memory,
            "cores": cores,
            "node": node.strip(),
            "sockets": sockets,
            "swap": swap,
        })
        await self._clients.instances.set_instance(config)
        try:
            await self._clients.secrets.create_instance_password(instance_id, password)
            return await self.enqueue(name="instance.create", payload={"id": instance_id})
        except Exception:
            await self._clients.instances.delete_instance(instance_id)
            raise

    async def create_sector(self, *, alias: str, cidr_block: str, storage: str) -> Job:
        """Atomically allocate the sector manifest and its Backplane resources."""
        if not all((alias.strip(), cidr_block.strip(), storage.strip())):
            raise ValueError("Name, CIDR, and storage are required.")
        try:
            config = await self._clients.sectors.create_with_backplane_allocation(
                alias=alias.strip(),
                cidr_block=IPv4Network(cidr_block.strip(), strict=True),
                storage=storage.strip(),
            )
            return await self.enqueue(name="sector.create", payload={"id": config.id})
        except Exception:
            # The manifest allocator commits resource ownership atomically; only
            # remove it if a later command-enqueue validation fails.
            if "config" in locals():
                await self._clients.sectors.delete(config.id)
            raise

    async def create_datacore(
        self, *, name: str, sector_id: str, storage: str, replicas: int, memory_gb: int, cores: int, capacity_gb: int,
    ) -> Job:
        """Create a DataCore manifest and secrets before its worker provisions it."""
        if not all((name.strip(), sector_id.strip(), storage.strip())):
            raise ValueError("Name, sector, and storage are required.")
        sector = await self._clients.sectors.get(sector_id)
        cluster_id = await self._clients.datacore.generate_cluster_id()
        rw_vip, ro_vip = await self._clients.sectors.acquire_vips(sector_id, count=2)
        config = models.DataCoreConfig(
            id=cluster_id, name=name.strip(), rw_virtual_router_id=rw_vip.virtual_router_id,
            ro_virtual_router_id=ro_vip.virtual_router_id, rw_vip=rw_vip.address, ro_vip=ro_vip.address,
            replicas=replicas, memory_gb=memory_gb, cores=cores, capacity_gb=capacity_gb,
            storage=storage.strip(), sector=sector_id, sector_name=sector.config.alias,
        )
        await self._clients.datacore.set_datacore(config)
        try:
            await asyncio.gather(
                self._clients.secrets.create_service_secret("datacore", cluster_id, subservice_name="superuser"),
                self._clients.secrets.create_service_secret("datacore", cluster_id, subservice_name="replication"),
            )
            return await self.enqueue(name="datacore.cluster.create", payload={"id": cluster_id})
        except Exception:
            await self._clients.datacore.delete(cluster_id)
            await self._clients.sectors.release_vips(rw_vip.virtual_router_id, ro_vip.virtual_router_id, id=sector_id)
            raise

    async def create_dockfs(
        self, *, name: str, sector_id: str, storage: str, capacity_gb: int, memory: int, cores: int, sockets: int,
    ) -> Job:
        """Create a DockFS manifest before the worker provisions active/passive nodes."""
        if not all((name.strip(), sector_id.strip(), storage.strip())):
            raise ValueError("Name, sector, and storage are required.")
        sector = await self._clients.sectors.get(sector_id)
        cluster_id = await self._clients.dockfs.generate_cluster_id()
        vip = await self._clients.sectors.acquire_vip(sector_id)
        config = models.DockFSConfig(
            id=cluster_id, name=name.strip(), virtual_router_id=vip.virtual_router_id, vip=vip.address,
            memory=memory, sockets=sockets, sector=sector_id, sector_name=sector.config.alias,
            cores=cores, capacity_gb=capacity_gb, storage=storage.strip(),
        )
        await self._clients.dockfs.set_dockfs(config)
        try:
            return await self.enqueue(name="dockfs.create", payload={"id": cluster_id})
        except Exception:
            await self._clients.dockfs.delete(cluster_id)
            await self._clients.sectors.release_vips(vip.virtual_router_id, id=sector_id)
            raise

    async def create_conduit_pool(self, *, name: str, sector_id: str, target_ids: list[str], port: int, balance: str) -> Job:
        """Persist an HTTP pool and queue its Conduit configuration work."""
        if not name.strip() or not sector_id.strip() or not target_ids:
            raise ValueError("Name, sector, and at least one compute target are required.")
        sector = await self._clients.sectors.get(sector_id)
        targets = []
        for target_id in target_ids:
            instance = await self._clients.instances.get_instance(target_id)
            if instance.config.sector != sector_id:
                raise ValueError(f"Compute target '{target_id}' is not in sector {sector_id}.")
            targets.append(models.InstanceTarget(instance_id=target_id))
        pool_id = await self._clients.conduit.generate_pool_id()
        config = models.ConduitPoolConfig(
            id=pool_id, type="http", name=name.strip(), sector=sector_id, sector_name=sector.config.alias,
            targets=targets, port=port, health_check=models.HealthCheck(port=port), balance=balance.strip() or "roundrobin",
        )
        await self._clients.conduit.set_pool(config)
        try:
            return await self.enqueue(name="conduit.pool.create", payload={"id": pool_id})
        except Exception:
            await self._clients.conduit.delete_pool(pool_id)
            raise

    async def create_conduit_endpoint(self, *, name: str, domain: str, sector_id: str, pool_id: str, endpoint_type: str) -> Job:
        """Persist a domain endpoint and queue its Conduit configuration work."""
        if not all((name.strip(), domain.strip(), sector_id.strip(), pool_id.strip())):
            raise ValueError("Name, domain, sector, and pool are required.")
        sector, pool = await asyncio.gather(self._clients.sectors.get(sector_id), self._clients.conduit.get_pool(pool_id))
        if pool.config.sector != sector_id:
            raise ValueError("The selected pool belongs to a different sector.")
        endpoint_id = await self._clients.conduit.generate_endpoint_id()
        config = models.ConduitEndpointConfig(
            id=endpoint_id, name=name.strip(), domain=domain.strip(), type=endpoint_type,
            sector=sector_id, sector_name=sector.config.alias, port=pool.config.port,
            pool=pool_id, pool_name=pool.config.name, rules=[models.RouterRule(host=domain.strip())],
        )
        await self._clients.conduit.set_endpoint(config)
        try:
            return await self.enqueue(name="conduit.endpoint.create", payload={"id": endpoint_id})
        except Exception:
            await self._clients.conduit.delete_endpoint(endpoint_id)
            raise

    async def create_custom_appliance(
        self, *, name: str, base_id: str, node: str, sector_id: str, disk_store: str, storage: str,
        cores: int, memory: int, swap: int, script: str, files: list[models.File] | None = None,
    ) -> Job:
        """Register a custom LXC appliance and queue its build workflow."""
        if not all((name.strip(), base_id.strip(), node.strip(), sector_id.strip(), disk_store.strip(), storage.strip())):
            raise ValueError("Name, base appliance, node, sector, and storage values are required.")
        base = await self._clients.appliances.get_appliance("base", base_id)
        if not base.state.volume_id:
            raise ValueError("The selected base appliance has not been downloaded.")
        appliance_id = await self._clients.appliances.generate_appliance_id("custom")
        steps: list[models.FileStep | models.ScriptStep] = []
        if script.strip():
            steps.append(models.ScriptStep(name="Configure appliance", script=script))
        if files:
            steps.append(models.FileStep(name="Copy uploaded files", files=files))
        config = models.CustomApplianceConfig(
            id=appliance_id, name=name.strip(), node=node.strip(), base_appliance_id=base_id,
            base_volume_id=base.state.volume_id, disk_store=disk_store.strip(), storage=storage.strip(),
            cores=cores, memory=memory, swap=swap, sector=sector_id, steps=steps,
        )
        await self._clients.appliances.set_appliance("custom", config)
        try:
            return await self.enqueue(name="appliance.custom", payload={"id": appliance_id})
        except Exception:
            await self._clients.appliances.delete_appliance("custom", appliance_id)
            raise

    async def create_custom_image(
        self, *, name: str, base_id: str, node: str, sector_id: str, disk_storage: str, storage: str,
        disk_size: int, cores: int, memory: int, script: str, files: list[models.File] | None = None,
    ) -> Job:
        """Register a custom VM image and queue its build workflow."""
        if not all((name.strip(), base_id.strip(), node.strip(), sector_id.strip(), disk_storage.strip(), storage.strip())):
            raise ValueError("Name, base image, node, sector, and storage values are required.")
        base = await self._clients.images.get_image("base", base_id)
        if not base.state.volume_id:
            raise ValueError("The selected base image has not been downloaded.")
        image_id = await self._clients.images.generate_image_id("custom")
        steps: list[models.FileStep | models.ScriptStep] = []
        if script.strip():
            steps.append(models.ScriptStep(name="Configure image", script=script))
        if files:
            steps.append(models.FileStep(name="Copy uploaded files", files=files))
        config = models.CustomImageConfig(
            id=image_id, name=name.strip(), base_image_id=base_id, base_volume_id=base.state.volume_id,
            node=node.strip(), disk_storage=disk_storage.strip(), disk_size=disk_size, storage=storage.strip(),
            memory=memory, cores=cores, sector=sector_id, steps=steps,
        )
        await self._clients.images.set_image("custom", config)
        try:
            return await self.enqueue(name="image.custom", payload={"id": image_id})
        except Exception:
            await self._clients.images.delete_image("custom", image_id)
            raise

    async def rotate_secret(self, *, name: str, value: str) -> None:
        if not value:
            raise ValueError("Enter a replacement secret value.")
        await self._clients.secrets.rotate(name, await self._clients.secrets.get_current_version(name), value)

    async def delete_resource(self, resource: str, resource_id: str) -> Job | None:
        """Perform safe direct deletes or enqueue a provider-facing delete operation."""
        workflow_actions: dict[str, tuple[str, dict[str, str]]] = {
            "compute": ("instance.state-change", {"id": resource_id, "desired_status": "terminate"}),
            "sectors": ("sector.delete", {"id": resource_id}),
            "datacore": ("datacore.cluster.delete", {"id": resource_id}),
            "dock-fs": ("dockfs.delete", {"id": resource_id}),
            "conduit": ("conduit.delete", {"id": resource_id}),
            "conduit-pools": ("conduit.pool.delete", {"id": resource_id}),
            "appliances": ("appliance.delete", {"id": resource_id, "appliance_type": "custom"}),
            "images": ("image.delete", {"id": resource_id, "image_type": "custom"}),
        }
        if resource in workflow_actions:
            name, payload = workflow_actions[resource]
            if resource in {"appliances", "images"}:
                client = self._clients.appliances if resource == "appliances" else self._clients.images
                try:
                    value = await (client.get_appliance("custom", resource_id) if resource == "appliances" else client.get_image("custom", resource_id))
                except Exception:
                    value = await (client.get_appliance("base", resource_id) if resource == "appliances" else client.get_image("base", resource_id))
                key = "appliance_type" if resource == "appliances" else "image_type"
                payload = {**payload, key: "custom" if hasattr(value.config, "name") else "base"}
            return await self.enqueue(name=name, payload=payload)
        direct_deletes: dict[str, Callable[[str], Awaitable[None]]] = {
            "secrets": self._clients.secrets.delete,
            "root-certificates": self._clients.pki.delete_root_certificate,
            "intermediate-certificates": self._clients.pki.delete_intermediate_certificate,
            "leaf-certificates": self._clients.pki.delete_leaf_certificate,
            "ssh-keys": self._clients.ssh_keys.delete_key_pair,
        }
        await direct_deletes[resource](resource_id)
        return None

    async def compute_action(self, action: str, resource_id: str) -> Job | str:
        """Queue an instance action or return its verified Proxmox deep link."""
        instance = await self._clients.instances.get_instance(resource_id)
        if action == "proxmox":
            if not instance.state.vmid:
                raise ValueError("This instance has not been assigned a VMID yet.")
            return await Proxmox().get_view_in_proxmox_url(vmid=instance.state.vmid, compute_type=instance.config.type)
        command = "instance.acquire-ip" if action == "refresh-ip" else "instance.state-change"
        payload: dict[str, Any] = {"id": resource_id}
        if command == "instance.state-change":
            payload["desired_status"] = action
        return await self.enqueue(name=command, payload=payload)

    async def sector_action(self, action: str, resource_id: str) -> Job:
        commands = {"create-conduit": "sector.conduit.create", "update-gateway": "sector.gateway.update"}
        return await self.enqueue(name=commands[action], payload={"id": resource_id})

    async def template_action(self, resource: str, action: str, resource_id: str) -> Job:
        """Queue generation or download for an existing template manifest."""
        commands = {
            ("appliances", "download"): "appliance.download",
            ("appliances", "build"): "appliance.custom",
            ("images", "download"): "image.download",
            ("images", "build"): "image.custom",
        }
        return await self.enqueue(name=commands[(resource, action)], payload={"id": resource_id})

    async def create_certificate_authority(self, subject: models.Subject) -> None:
        from orbitlab.data_types import KeyUsageTypes

        await self._clients.pki.create_certificate_authority(subject, [KeyUsageTypes.DIGITAL_SIGNATURE, KeyUsageTypes.KEY_CERT_SIGN, KeyUsageTypes.CRL_SIGN])

    async def create_intermediate_certificate(self, common_name: str, root: str, domain_constraint: str) -> None:
        await self._clients.pki.create_intermediate_certificate(common_name, root, domain_constraint)

    async def create_leaf_certificate(self, common_name: str, signer: str, san_dns: list[str], san_ips: list[str]) -> None:
        await self._clients.pki.create_leaf_certificate(common_name, san_dns, san_ips, signer, server_auth=True)

    async def create_ssh_key(self, name: str, key_type: str) -> None:
        from orbitlab.data_types import SSHKeyTypes

        await self._clients.ssh_keys.create_key_pair(name, SSHKeyTypes(key_type))


class Clients(SimpleNamespace):
    """Focused Redis clients owned by the NiceGUI application lifecycle."""

    def __init__(self) -> None:
        redis = _redis_connection()
        super().__init__(
            redis=redis,
            cluster=_bind_redis(ClusterClient(), redis),
            backplane=_bind_redis(BackplaneClient(), redis),
            nodes=_bind_redis(ClusterClient(), redis),
            sectors=_bind_redis(SectorClient(), redis),
            instances=_bind_redis(InstanceClient(), redis),
            datacore=_bind_redis(DataCoreClient(), redis),
            dockfs=_bind_redis(DockFSClient(), redis),
            conduit=_bind_redis(ConduitClient(), redis),
            appliances=_bind_redis(ApplianceClient(), redis),
            images=_bind_redis(ImagesClient(), redis),
            autoscaling=_bind_redis(AutoscalingClient(), redis),
            secrets=_bind_redis(SecretsClient(), redis),
            pki=_bind_redis(PKIClient(), redis),
            ssh_keys=_bind_redis(SSHKeyClient(), redis),
            logs=_bind_redis(LogsClient(), redis),
        )
        self.queries = Queries(self)
        self.commands = Commands(self)

    async def gather_inventory(self) -> tuple[Any, Any, Any, Any, Any, Any]:
        """Read independent dashboard inventories concurrently."""
        return await asyncio.gather(
            self.nodes.list_nodes(), self.sectors.list_sectors(), self.instances.list_instances(),
            self.datacore.list_datacores(), self.dockfs.list_dockfs_clusters(), self.conduit.list_endpoints(),
        )

    async def close(self) -> None:
        """Close the application-owned Redis connection."""
        await self.redis.aclose()
