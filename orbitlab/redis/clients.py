import asyncio
import base64
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from functools import cached_property
import hashlib
from inspect import isawaitable
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, ip_address
import json
import os
import secrets
import string
import time
from typing import Final, Literal, TypeVar, cast, overload

from cryptography import x509
from pydantic import BaseModel
from redis import WatchError
from redis.asyncio.client import Redis, Pipeline
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.keywrap import aes_key_wrap, aes_key_unwrap
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa, x25519

from orbitlab import data_types
from orbitlab.constants import EventStreams
from orbitlab.redis import models, exceptions


T = TypeVar("T", bound=BaseModel)
RC = TypeVar("RC", bound=models.ResourceConfig)


class RedisClient:
    def __init__(self) -> None:
        self._cas_max_retries = 8
    
    @cached_property
    def client(self) -> Redis:
        if os.environ.get("ORBITLAB_DEV"):
            return Redis.from_url(os.environ["ORBITLAB_REDIS_URL"])
        return Redis(db=10)
    
    async def log(self, message: str, level: Literal["Info", "Warning", "Error"] = "Info") -> None:
        # TODO: Log to SYSTEM logs instead of printing.
        print(f"{datetime.now(UTC).isoformat()} - {level} - {self.__class__.__name__} - {message}")
    
    async def _mutate_object(self, name: str, submitted: models.ResourceConfig) -> None:
        for attempt in range(1, self._cas_max_retries + 1):
            await self.log(f"{name} mutation attempt #{attempt} of {self._cas_max_retries + 1}")
            async with self.client.pipeline(transaction=True) as pipeline:
                try:
                    await pipeline.watch(name)
                    if raw := await self._get_decoded(name=name, key="config", pipeline=pipeline):
                        current = type(submitted).model_validate_json(raw)
                        await self.log(f"Found existing {name} config version {current.version}@{current.last_update}")
                        if current == submitted:
                            await self.log(f"No changes for config {name}")
                            await pipeline.unwatch()
                            return
                    else:
                        await self.log(f"New configuration for {name}")
                        current = submitted
                    
                    if current.version != submitted.version:
                        raise RuntimeError(
                            f"CAS conflict for '{name}': "
                            f"submitted version={submitted.version}, "
                            f"Redis version={current.version}"
                        )
                    new_version = submitted.model_copy(
                        update={"version": submitted.version + 1, "last_update": int(time.time())}
                    )
                    await self.log(f"Updating config {name} to version {new_version.version}@{new_version.last_update}")
                    pipeline.multi()
                    _hset = pipeline.hset(name=name, key="config", value=new_version.model_dump_json())
                    if isawaitable(_hset):
                        await _hset
                    await pipeline.execute()
                    await self.log(f"Config {name} update complete.")
                    return
                except WatchError:
                    await self.log(level="Warning", message=f"Attempt #{attempt} failed. Retrying...")
                    await asyncio.sleep(1)
                    continue
        raise RuntimeError(
            f"CAS update failed after {self._cas_max_retries} retries due to contention: {name}"
        )

    async def _list_keys(self, name: str, *, ignore_config: bool = False, pipeline: Pipeline | None = None) -> list[str]:
        if pipeline:
            value = pipeline.hkeys(name=name)
        else:
            value = self.client.hkeys(name=name)
        if isawaitable(value):
            value = await value
        value = cast("list[bytes]", value)
        if ignore_config:
            return [key.decode() for key in value if key != "config"]
        return [key.decode() for key in value]

    async def _get_decoded(self, name: str, key: str, *, pipeline: Pipeline | None = None) -> str | None:
        if pipeline:
            value = pipeline.hget(name=name, key=key)
        else:
            value = self.client.hget(name=name, key=key)
            
        if isawaitable(value):
            value = await value
            
        if not value:
            return None
        
        value = cast("bytes", value)
        return value.decode()

    async def _get_state(self, name: str, model: type[T]) -> T:
        state = {
            key: await self._get_decoded(name=name, key=key) for key in await self._list_keys(name=name, ignore_config=True)
        }
        return model.model_validate(state)

    async def _get_config(self, name: str, model: type[T]) -> T | None:
        value = self.client.hget(name=name, key="config")
        if isawaitable(value):
            value = await value

        if not value:
            return None
        
        value = cast("bytes", value)
        resource = json.loads(value.decode())
        resource["state"] = {
            key: await self._get_decoded(name=name, key=key) for key in await self._list_keys(name=name, ignore_config=True)
        }
        return model.model_validate(resource)

    async def _set_add(self, index: str, *values: str) -> None:
        _res = self.client.sadd(index, *values)
        if isawaitable(_res):
            await _res

    async def _set_rem(self, index, *values: str) -> None:
        _res = self.client.srem(index, *values)
        if isawaitable(_res):
            await _res

    async def _hset(self, name: str, key: str, value: bytes | str | int) -> None:
        _res = self.client.hset(
            name=name,
            key=key,
            value=value.decode() if isinstance(value, bytes) else str(value),
        )
        if isawaitable(_res):
            await _res

    async def _hdel(self, name: str, key: str) -> None:
        _res = self.client.hdel(name, key)
        if isawaitable(_res):
            await _res

    async def _list_set_members(self, index: str) -> list[str]:
        members = self.client.smembers(name=index)
        if isawaitable(members):
            members = await members
        members = cast("list[bytes]", members)
        return [member.decode() for member in members]

    async def _generate_unique_id(self, prefix: str, *, count: int = 12, index: str = "", existing: list[str] | None = None) -> str:
        if not existing:
            existing = await self._list_set_members(index=index)
        
        if not index and not existing:
            random_id = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(count))
            return f"{prefix}-{random_id}"

        while True:
            random_id = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(count))
            resource_id = f"{prefix}-{random_id}"
            if resource_id not in existing:
                break
        return resource_id


class ClusterClient(RedisClient):
    NAME: Final = "ol:cluster"
    INDEX: Final = "ol:cluster:nodes"
    DOMAIN_PROVIDERS: Final = "ol:cluster:domain_providers"

    def _get_node_redis_name(self, node: str) -> str:
        return f"{self.INDEX}:{node}"

    async def is_initialized(self) -> bool:
        return bool(await self._get_decoded(name=self.NAME, key="initialized"))

    async def set_initialized(self) -> None:
        await self._hset(name=self.NAME, key="initialized", value="True")

    async def set_lan_network(self, network: IPv4Network) -> None:
        await self._hset(name=self.NAME, key="lan-network", value=str(network))
    
    async def get_lan_network(self) -> IPv4Network:
        if network := await self._get_decoded(name=self.NAME, key="lan-network"):
            return IPv4Network(network)
        raise exceptions.ResourceNotFoundError(name=self.NAME, key="lan-network")

    async def lan_network_configured(self) -> bool:
        try:
            await self.get_lan_network()
        except exceptions.ResourceNotFoundError:
            return False
        else:
            return True

    async def get_defaults(self) -> models.Defaults:
        if defaults := await self._get_decoded(name=self.NAME, key="defaults"):
            return models.Defaults.model_validate_json(defaults)
        raise exceptions.ResourceNotFoundError(name=self.NAME, key="defaults")

    async def set_defaults(self, defaults: models.Defaults) -> None:
        await self._hset(name=self.NAME, key="defaults", value=defaults.model_dump_json())

    async def defaults_exist(self) -> bool:
        try:
            await self.get_defaults()
        except exceptions.ResourceNotFoundError:
            return False
        else:
            return True

    async def get_infra_appliances(self) -> models.InfraAppliances:
        if appliances := await self._get_decoded(name=self.NAME, key="appliances"):
            return models.InfraAppliances.model_validate_json(appliances)
        raise exceptions.ResourceNotFoundError(name=self.NAME, key="appliances")
    
    async def infra_exists(self) -> bool:
        try:
            await self.get_infra_appliances()
        except exceptions.ResourceNotFoundError:
            return False
        else:
            return True
    
    async def set_infra_appliances(self, appliances: models.InfraAppliances) -> None:
        await self._hset(name=self.NAME, key="appliances", value=appliances.model_dump_json())

    async def set_node(self, node: models.NodeConfig) -> None:
        name = self._get_node_redis_name(node=node.name)
        await self._mutate_object(name=name, submitted=node)
        await self._set_add(self.INDEX, node.name)

    async def get_node(self, node: str) -> models.Node:
        name = self._get_node_redis_name(node=node)
        if config := await self._get_config(name=name, model=models.NodeConfig):
            state = await self._get_state(name=name, model=models.NodeState)
            return models.Node(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name, key="config")
    
    async def set_node_online(self, node: str, online: bool) -> None:
        name = self._get_node_redis_name(node=node)
        await self._hset(name=name, key="online", value=1 if online else 0)
    
    async def set_node_maintenance_mode(self, node: str, maintenance_mode: bool) -> None:
        name = self._get_node_redis_name(node=node)
        await self._hset(name=name, key="maintenance_mode", value=1 if maintenance_mode else 0)
    
    async def list_nodes(self) -> list[models.Node]:
        return [await self.get_node(node=node) for node in await self._list_set_members(index=self.INDEX)]

    async def add_domain_provider(self, domain_provider: models.DomainProvider) -> None:
        await self._hset(
            name=f"{self.DOMAIN_PROVIDERS}:configs",
            key=domain_provider.name,
            value=domain_provider.model_dump_json(),
        )
        await self._set_add(self.DOMAIN_PROVIDERS, domain_provider.name)

    async def get_domain_provider(self, name: str) -> models.DomainProvider:
        if domain_provider := await self._get_decoded(name=f"{self.DOMAIN_PROVIDERS}:configs", key=name):
            return models.DomainProvider.model_validate_json(domain_provider)
        raise exceptions.ResourceNotFoundError(name=self.DOMAIN_PROVIDERS, key=name)

    async def domain_provider_exists(self, name: str) -> bool:
        try:
            await self.get_domain_provider(name=name)
        except exceptions.ResourceNotFoundError:
            return False
        else:
            return True

    async def list_domain_providers(self) -> list[models.DomainProvider]:
        return [
            await self.get_domain_provider(name=name)
            for name in await self._list_set_members(index=self.DOMAIN_PROVIDERS)
        ]

    async def delete_domain_provider(self, name: str) -> None:
        await asyncio.gather(
            self._hdel(f"{self.DOMAIN_PROVIDERS}:configs", name),
            SecretsClient().delete_service_secret(service_name="domain_provider", service_id=name),
            self._set_rem(self.DOMAIN_PROVIDERS, name),
        )


class BackplaneClient(RedisClient):
    NAME: Final = "ol:backplane"
    ASSIGNMENTS_INDEX: Final = "ol:backplane:assignments"
    TAGS_INDEX: Final = "ol:backplane:vlan-tags"
    VRID_INDEX: Final = "ol:backplane:vrid"
    
    RESERVED_INFRA_IPS: Final = 10
    RESERVED_BROADCAST_IPS: Final = -5

    async def exists(self) -> bool:
        return bool(await self._get_config(name=self.NAME, model=models.BackplaneConfig))

    async def get(self) -> models.Backplane:
        if config := await self._get_config(name=self.NAME, model=models.BackplaneConfig):
            state = await self._get_state(name=self.NAME, model=models.BackplaneState)
            return models.Backplane(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=self.NAME)

    async def set(self, backplane: models.BackplaneConfig) -> None:
        await self._mutate_object(name=self.NAME, submitted=backplane)

    async def set_appliance_version(self, version: str) -> None:
        await self._hset(name=self.NAME, key="version", value=version)

    async def get_appliance_version(self) -> str:
        if version := await self._get_decoded(name=self.NAME, key="version"):
            return version
        return ""

    async def get_next_vlan_tag(self, start: int = 1000, end: int = 9999) -> int | None:
        existing_tags = [int(tag) for tag in await self._list_set_members(index=self.TAGS_INDEX)]
        if tag := next((i for i in range(start, end + 1) if i not in existing_tags), None):
            await self.add_used_vlan_tags(tags=[tag])
            return tag
        return None

    async def add_used_vlan_tags(self, tags: list[int]) -> None:
        if tags:
            await self._set_add(self.TAGS_INDEX, *[str(tag) for tag in tags])

    async def release_vlan_tag(self, tag: int) -> None:
        await self._set_rem(self.TAGS_INDEX, str(tag))

    async def get_vmid(self) -> int:
        if vmid := await self._get_decoded(name=self.NAME, key="vmid"):
            return int(vmid)
        raise exceptions.ResourceNotFoundError(name="VMID")

    async def set_vmid(self, vmid: int) -> None:
        await self._hset(name=self.NAME, key="vmid", value=vmid)

    async def backplane_controller_exists(self) -> bool:
        try:
            await self.get_vmid()
        except exceptions.ResourceNotFoundError:
            return False
        else:
            return True

    @overload
    async def get_next_available_ip(self, *, count: None = None) -> IPv4Interface: ...

    @overload
    async def get_next_available_ip(self, *, count: int) -> list[IPv4Interface]: ...

    async def get_next_available_ip(self, *, count: int | None = None) -> IPv4Interface | list[IPv4Interface]:
        """Get the next available IP address in the subnet."""
        backplane = await self.get()
        assigned = [IPv4Interface(address).ip for address in await self._list_set_members(index=self.ASSIGNMENTS_INDEX)]
        hosts = list(backplane.config.cidr_block.hosts())
        usable = hosts[self.RESERVED_INFRA_IPS:self.RESERVED_BROADCAST_IPS]
        if count:
            available_generator = iter(
                IPv4Interface(f"{ip}/{backplane.config.cidr_block.prefixlen}") for ip in usable if ip not in assigned
            )
            assigned = [next(available_generator) for _ in range(count)]
            await self._set_add(self.ASSIGNMENTS_INDEX, *[str(ip) for ip in assigned])
            return assigned
        assigned = next(iter(
            IPv4Interface(f"{ip}/{backplane.config.cidr_block.prefixlen}") for ip in usable if ip not in assigned
        ))
        await self._set_add(self.ASSIGNMENTS_INDEX, str(assigned))
        return assigned

    async def release_assigned_ips(self, *addresses: IPv4Interface) -> None:
        await self._set_rem(self.ASSIGNMENTS_INDEX, *[str(address) for address in addresses])

    async def get_next_available_vrid(self) -> int:
        assigned = [int(vrid) for vrid in await self._list_set_members(index=self.VRID_INDEX)]
        vrid = next(iter([vrid for vrid in range(1, 256) if vrid not in assigned]))
        await self._set_add(self.VRID_INDEX, str(vrid))
        return vrid

    async def release_assigned_vrids(self, *vrids: int) -> None:
        await self._set_rem(self.VRID_INDEX, *[str(vrid) for vrid in vrids])

    async def set_relay_ping(self, vmid: int) -> None:
        await self._hset(name=self.NAME, key="relay-ping", value=vmid)

    async def get_relay_ping(self) -> int:
        if vmid := await self._get_decoded(name=self.NAME, key="relay-ping"):
            return int(vmid)
        return 0

    async def generate_backplane_params(self, vmid: int) -> dict:
        backplane = await self.get()
        infra = await ClusterClient().get_infra_appliances()
        storage = (await ClusterClient().get_defaults()).vztmpl
        return {
            "features": "nesting=1",
            "ostemplate": infra.appliances["backplane"].volume_id,
            "hostname": "orbitlab-backplane",
            "cores": 1,
            "memory": 512,
            "swap": 512,
            "net0": (
                f"name=eth0,"
                f"bridge={backplane.config.vnet_id},"
                f"ip={backplane.config.dns_address},"
                f"gw={backplane.config.default_gateway.ip}"
            ),
            "net1": (
                f"name=eth1,"
                f"bridge={backplane.config.vnet_id},"
                f"ip={backplane.config.orbital_relay_address},"
                f"gw={backplane.config.default_gateway.ip}"
            ),
            "rootfs": f"{storage}:8",
            "unprivileged": "1",
            "vmid": vmid,
            "password": SecretsClient.generate_random_password(),
            "searchdomain": "orbitlab.internal",
            "onboot": "1",
        }


class ETCDClient(RedisClient):
    NAME: Final = "ol:etcd"
    MEMBER_INDEX: Final = "ol:etcd:members"

    async def list_members(self) -> list[models.ETCDMember]:
        return [
            models.ETCDMember.model_validate_json(member)
            for member in await self._list_set_members(index=self.MEMBER_INDEX)
        ]
    
    async def get_random_member(self) -> models.ETCDMember:
        member = self.client.srandmember(name=self.MEMBER_INDEX)
        if isawaitable(member):
            member = await member
        member = cast("str | None", member)
        if member:
            return models.ETCDMember.model_validate_json(member)
        raise exceptions.ResourceNotFoundError(name=self.MEMBER_INDEX)
    
    async def get_member_by_vmid(self, vmid: int) -> models.ETCDMember:
        members = await self.list_members()
        if member := next(iter(member for member in members if member.vmid == vmid), None):
            return member
        raise exceptions.ResourceNotFoundError(name=f"{self.MEMBER_INDEX}:{vmid}")
    
    async def generate_create_params(self, vmid: int) -> dict:
        cluster = ClusterClient()
        
        infra = await cluster.get_infra_appliances()
        defaults = await cluster.get_defaults()
        backplane = await BackplaneClient().get()
        member = models.ETCDMember(
            vmid=vmid,
            name=await self._generate_unique_id(
                prefix="etcd",
                existing=[member.name for member in await self.list_members()],
            ),
            address=await BackplaneClient().get_next_available_ip()
        )
        await self._set_add(self.MEMBER_INDEX, member.model_dump_json())
        return {
            "pool": "orbitlab-etcd",
            "features": "nesting=1",
            "ostemplate": infra.appliances["etcd"].volume_id,
            "hostname": member.name,
            "cores": 1,
            "memory": 512,
            "swap": 512,
            "net0": (
                f"name=eth0,bridge={backplane.config.vnet_id},ip={member.address},gw={backplane.config.default_gateway.ip}"
            ),
            "rootfs": f"{defaults.vztmpl}:8",
            "unprivileged": "1",
            "vmid": vmid,
            "password": SecretsClient.generate_random_password(),
            "searchdomain": "orbitlab.internal",
            "nameserver": f"{backplane.config.dns_address.ip}",
            "onboot": "1",
        }

    async def remove_member(self, member: models.ETCDMember) -> None:
        await self._set_rem(self.MEMBER_INDEX, member.model_dump_json())

    async def get_version(self) -> str:
        if version := await self._get_decoded(name=self.NAME, key="version"):
            return version
        return ""

    async def set_version(self, version: str) -> None:
        await self._hset(name=self.NAME, key="version", value=version)

    async def get_status(self) -> data_types.ETCDStatus:
        if status := await self._get_decoded(name=self.NAME, key="status"):
            return data_types.ETCDStatus(status)
        return data_types.ETCDStatus.PENDING

    async def set_status(self, status: data_types.ETCDStatus) -> None:
        await self._hset(name=self.NAME, key="status", value=status)

    async def delete(self) -> None:
        await self.client.delete(self.NAME, self.MEMBER_INDEX)


class DNSClient(RedisClient):
    """https://coredns.io/explugins/redis/.
    """
    BACKPLANE_ZONE: Final = "orbitlab.internal"
    SECTOR_ZONE: Final = "sector.internal"

    def _zone_name(self, zone_type: data_types.ZoneType, sector_id: str = "") -> str:
        if sector_id:
            return f"_{zone_type}:{sector_id}.{self.SECTOR_ZONE}."
        return f"_{zone_type}:{self.BACKPLANE_ZONE}."

    async def zone_exists(self, zone_type: data_types.ZoneType, sector_id: str = "") -> bool:
        if sector_id:
            name = self._zone_name(zone_type="internal", sector_id=sector_id)
        else:
            name = self._zone_name(zone_type=zone_type)
        return bool(await self._get_decoded(name=name, key="@"))
            
    async def create_backplane_zone(self, zone_type: data_types.ZoneType = "internal") -> None:
        if not await self.zone_exists(zone_type=zone_type):
            name = self._zone_name(zone_type=zone_type)
            backplane = await BackplaneClient().get()
            await self._hset(
                name=name,
                key="@",
                value=models.ZoneDefinitionRecords(zone=self.BACKPLANE_ZONE).model_dump_json(),
            )
            await self._hset(
                name=name,
                key="ns",
                value=models.ARecord(ip=backplane.config.dns_address.ip).model_dump_json(),
            )
    
    async def create_sector_zone(self, sector_id: str) -> None:
        if not await self.zone_exists(zone_type="internal", sector_id=sector_id):
            name = self._zone_name(zone_type="internal", sector_id=sector_id)
            sector = await SectorClient().get(id=sector_id)
            await self._hset(
                name=name,
                key="@",
                value=models.ZoneDefinitionRecords(zone=self.SECTOR_ZONE).model_dump_json(),
            )
            await self._hset(
                name=name,
                key="ns",
                value=models.ARecord(ip=sector.config.dns_address.ip).model_dump_json(),
            )

    async def delete_sector_zone(self, sector_id: str) -> None:
        name = self._zone_name(zone_type="internal", sector_id=sector_id)
        await self.client.delete(name)

    async def add_backplane_a_records(self, hostname: str, *records: models.ARecord, zone_type: data_types.ZoneType = "internal") -> None:
        name = self._zone_name(zone_type=zone_type)
        if existing := await self._get_decoded(name=name, key=hostname):
            a_records = models.ARecords.model_validate_json(existing)
        else:
            a_records = models.ARecords()
        a_records.add(*records)
        await self._hset(name=name, key=hostname, value=a_records.model_dump_json())

    async def remove_backplane_a_records(self, hostname: str, *records: models.ARecord, zone_type: data_types.ZoneType = "internal") -> None:
        name = self._zone_name(zone_type=zone_type)
        if existing := await self._get_decoded(name=name, key=hostname):
            a_records = models.ARecords.model_validate_json(existing)
            a_records.remove(*records)
            if a_records.valid:
                await self._hset(name=name, key=hostname, value=a_records.model_dump_json())
            else:
                await self._hdel(name, hostname)

    async def add_backplane_srv_records(self, service: str, protocol: Literal["tcp", "udp"], *records: models.SRVRecord) -> None:
        name = self._zone_name(zone_type="internal")
        hostname = f"_{service}._{protocol}"
        if existing := await self._get_decoded(name=name, key=hostname):
            srv_records = models.SRVRecords.model_validate_json(existing)
        else:
            srv_records = models.SRVRecords()
        srv_records.add(*records)
        await self._hset(name=name, key=hostname, value=srv_records.model_dump_json())

    async def remove_backplane_srv_records(self, service: str, protocol: Literal["tcp", "udp"], *records: models.SRVRecord) -> None:
        name = self._zone_name(zone_type="internal")
        hostname = f"_{service}._{protocol}"
        if existing := await self._get_decoded(name=name, key=hostname):
            srv_records = models.SRVRecords.model_validate_json(existing)
            srv_records.remove(*records)
            if srv_records.valid:
                await self._hset(name=name, key=hostname, value=srv_records.model_dump_json())
            else:
                await self._hdel(name, hostname)  

    async def delete_backplane_records(self, *hostnames: str, zone_type: data_types.ZoneType = "internal") -> None:
        name = self._zone_name(zone_type=zone_type)
        await self._hdel(name, *hostnames)

    async def add_instance_dhcp_record(self, sector_id: str, address: IPv4Address) -> None:
        name = self._zone_name(zone_type="internal", sector_id=sector_id)
        if not await self.zone_exists(zone_type="internal", sector_id=sector_id):
            raise exceptions.ResourceNotFoundError(name=name)
        value = models.ARecords(a=[models.ARecord(ip=address)]).model_dump_json()
        await self._hset(name=name, key=f"ip-{str(address).replace('.', '-')}", value=value)

    async def delete_instance_dhcp_record(self, sector_id: str, address: IPv4Address) -> None:
        name = self._zone_name(zone_type="internal", sector_id=sector_id)
        if not await self.zone_exists(zone_type="internal", sector_id=sector_id):
            raise exceptions.ResourceNotFoundError(name=name)
        await self._hdel(name, f"ip-{str(address).replace('.', '-')}")

    async def add_sector_a_records(self, sector_id: str, hostname: str, *records: models.ARecord) -> None:
        """Add one or multiple 'A' Records to a given sector's DNS.
        
        All records specified will be added to the same `hostname`. This allows for creating 'A' records
        that resolve to multiple IPv4 addresses. The provided hostname MUST NOT HAVE the `sector.internal`
        provided at function call. So, if you want a record of `my-host.sector.internal`, the `hostname` 
        should just be set to `"my-host"`. 
        
        Args:
            sector_id (str): The given Sector ID in `olvnXXXX` format, where the XXXX is the VLAN tag.
            hostname (str): The hostname record to create.
            *records (tuple[ARecord]): The 'A' records to assign to the given hostname.
        
        Raises:
            ResourceNotFoundError: If the sector zone does not exist.
        """
        name = self._zone_name(zone_type="internal", sector_id=sector_id)
        
        if not await self.zone_exists(zone_type="internal", sector_id=sector_id):
            raise exceptions.ResourceNotFoundError(name=name)

        if existing := await self._get_decoded(name=name, key=hostname):
            a_records = models.ARecords.model_validate_json(existing)
        else:
            a_records = models.ARecords()
        a_records.add(*records)
        await self._hset(name=name, key=hostname, value=a_records.model_dump_json())

    async def delete_sector_a_record(self, sector_id: str, hostname: str) -> None:
        name = self._zone_name(zone_type="internal", sector_id=sector_id)
        if not await self.zone_exists(zone_type="internal", sector_id=sector_id):
            raise exceptions.ResourceNotFoundError(name=name)
        await self._hdel(name, hostname)

    async def remove_sector_a_records(self, sector_id: str, hostname: str, *records: models.ARecord) -> None:
        name = self._zone_name(zone_type="internal", sector_id=sector_id)
        
        if not await self.zone_exists(zone_type="internal", sector_id=sector_id):
            raise exceptions.ResourceNotFoundError(name=name)
        
        if existing := await self._get_decoded(name=name, key=hostname):
            a_records = models.ARecords.model_validate_json(existing)
            a_records.remove(*records)
            if a_records.valid:
                await self._hset(name=name, key=hostname, value=a_records.model_dump_json())
            else:
                await self._hdel(name, hostname)


class SectorClient(RedisClient):
    INDEX: Final = "ol:sectors"
    
    def _get_name(self, id: str) -> str:
        return f"ol:sector:{id}"
    
    async def list_sectors(self) -> list[models.Sector]:
        return [await self.get(id=id) for id in await self._list_set_members(index=self.INDEX)]
    
    async def sector_exists(self, id: str) -> bool:
        return id in await self._list_set_members(index=self.INDEX)
    
    async def get(self, id: str) -> models.Sector:
        name = self._get_name(id=id)
        if config := await self._get_config(name=name, model=models.SectorConfiguration):
            state = await self._get_state(name=name, model=models.SectorState)
            return models.Sector(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name)

    async def create(self, config: models.SectorConfiguration) -> None:
        name = self._get_name(id=config.id)
        await self._mutate_object(name=name, submitted=config)
        await self._set_add(self.INDEX, config.id)

    async def update(self, config: models.SectorConfiguration) -> None:
        return await self.create(config=config)

    async def generate_params(self, id: str, vmid: int, appliance: Literal["gateway", "conduit", "wardlink"]) -> dict[str, str]:
        name = self._get_name(id=id)
        if config := await self._get_config(name=name, model=models.SectorConfiguration):
            match appliance:
                case "gateway":
                    backplane = await BackplaneClient().get()
                    address = await BackplaneClient().get_next_available_ip()
                    params = {
                        "net0": f"name=eth0,bridge={config.bridge},ip={config.default_gateway}",
                        "net1": (
                            f"name=eth1,bridge={backplane.config.vnet_id},ip={address},gw={backplane.config.default_gateway.ip}"
                        ),
                        "net2": f"name=eth2,bridge={config.bridge},ip={config.dns_address}",
                        "nameserver": str(backplane.config.dns_address.ip),
                        "hostname": f"gateway-{config.bridge}",
                    }
                case "conduit":
                    params = {
                        "net0": f"name=eth0,hwaddr={config.conduit_internal_mac},bridge={config.bridge},ip=dhcp",
                        "net1": f"name=eth1,hwaddr={config.conduit_external_mac},bridge=vmbr0,ip=dhcp",
                        "nameserver": str(config.dns_address.ip),
                        "hostname": f"conduit-{config.bridge}",
                    }
                case "wardlink":
                    params = {
                        "net0": f"name=eth0,hwaddr={config.wardlink_internal_mac},bridge={config.bridge},ip=dhcp",
                        "net1": f"name=eth1,hwaddr={config.wardlink_external_mac},bridge=vmbr0,ip=dhcp",
                        "nameserver": str(config.dns_address.ip),
                        "hostname": f"wardlink-{config.bridge}",
                    }
                case _:
                    msg = f"Unexpected appliance type: {appliance}"
                    raise ValueError(msg)
            
            infra = await ClusterClient().get_infra_appliances()
            params.update({
                "features": "nesting=1",
                "ostemplate": infra.appliances[appliance].volume_id,
                "cores": "1",
                "memory": "512",
                "swap": "512",
                "rootfs": f"{config.storage}:8",
                "unprivileged": "1",
                "vmid": str(vmid),
                "password": SecretsClient.generate_random_password(),
                "searchdomain": "sector.internal",
                "onboot": "1",
            })
            return params
        raise exceptions.ResourceNotFoundError(name=name)
    
    async def get_vmid(self, id: str, appliance: Literal["gateway", "conduit", "wardlink"]) -> int:
        name = self._get_name(id=id)
        if vmid := await self._get_decoded(name=name, key=f"{appliance}_vmid"):
            return int(vmid)
        return 0
    
    async def set_vmid(self, id: str, appliance: Literal["gateway", "conduit", "wardlink"], vmid: int) -> None:
        name = self._get_name(id=id)
        await self._hset(name=name, key=f"{appliance}_vmid", value=vmid)
    
    async def set_version(self, id: str, appliance: Literal["gateway", "conduit", "wardlink"], version: str) -> None:
        await self._hset(name=self._get_name(id=id), key=f"{appliance}_version", value=version)
    
    async def get_version(self, id: str, appliance: Literal["gateway", "conduit", "wardlink"]) -> str:
        if version := await self._get_decoded(name=self._get_name(id=id), key=f"{appliance}_version"):
            return version
        return ""
    
    async def set_status(self, id: str, appliance: Literal["gateway", "conduit", "wardlink"], status: str) -> None:
        name = self._get_name(id=id)
        await self._hset(name=name, key=f"{appliance}_status", value=status)
    
    async def set_sector_status(self, id: str, status: data_types.SectorStatus) -> None:
        await self._hset(name=self._get_name(id=id), key="status", value=status)
    
    async def get_sector_status(self, id: str) -> data_types.SectorStatus:
        if status := await self._get_decoded(name=self._get_name(id=id), key="status"):
            return data_types.SectorStatus(status)
        return data_types.SectorStatus.PENDING
    
    async def get_wardlink_cidr(self, id: str) -> IPv4Network:
        name = self._get_name(id=id)
        if cidr := await self._get_decoded(name=name, key="wardlink_cidr"):
            return IPv4Network(cidr)
        
        if config := await self._get_config(name=name, model=models.SectorConfiguration):
            backplane = await BackplaneClient().get()
            lan_cidr = await ClusterClient().get_lan_network()
            blocked = (config.cidr_block, lan_cidr, backplane.config.cidr_block)
            private_address_space = IPv4Network("100.64.0.0/10")
            for candidate in private_address_space.subnets(new_prefix=24):
                if not any(candidate.overlaps(network) for network in blocked):
                    return candidate
            msg = f"Unable to find available address in {private_address_space}"
            raise ValueError(msg)
        raise exceptions.ResourceNotFoundError(name=name)
    
    async def add_wardlink_client(self, id: str, name: str) -> models.WardLinkClient:
        sector = await self.get(id=id)
        address = sector.get_new_wardlink_client_address()
        index = len(sector.state.wardlink_clients)
        secret = await SecretsClient().create_wardlink_keypair(sector=id, name=name)
        client = models.WardLinkClient(index=index, name=name, address=address, secret=secret.name)
        sector.state.wardlink_clients[name] = client
        state_dict = sector.state.model_dump()
        await self._hset(name=self._get_name(id=id), key="wardlink_clients", value=json.dumps(state_dict["wardlink_clients"]))
        return client
    
    async def acquire_vip(self, id: str) -> models.SectorVIP:
        name = self._get_name(id=id)
        sector = await self.get(id=id)
        vip = sector.get_available_vip()
        sector.state.vips[vip.virtual_router_id] = vip.address
        serialized = sector.state.model_dump()
        await self._hset(name=name, key="vips", value=json.dumps(serialized["vips"]))
        return vip

    async def release_vips(self, *virtual_router_ids: int, id: str) -> None:
        name = self._get_name(id=id)
        sector = await self.get(id=id)
        sector.state.vips = {vrid: vip for vrid, vip in sector.state.vips.items() if vrid not in virtual_router_ids}
        if sector.state.vips:
            serialized = sector.state.model_dump()
            await self._hset(name=name, key="vips", value=json.dumps(serialized["vips"]))
        else:
            await self._hdel(name, "vips")

    async def delete(self, id: str) -> None:
        name = self._get_name(id=id)
        if config := await self._get_config(name=name, model=models.SectorConfiguration):
            await BackplaneClient().release_vlan_tag(tag=config.tag)
            await BackplaneClient().release_assigned_ips(config.backplane_address)             
            await self.client.delete(name)
            await self._set_rem(self.INDEX, id)


class SecretsClient(RedisClient):
    INDEX: Final = "ol:secrets"
    PKI_KEY_INDEX: Final = "ol:secrets:pki"
    
    def _get_name(self, secret_name: str) -> str:
        return f"ol:secrets:{secret_name}"
    
    def _get_service_secret_name(self, service_name: str, service_id: str, subservice_name: str) -> str:
        secret_name = f"/orbitlab/{service_name}/{service_id}"
        if subservice_name:
            secret_name += f"/{subservice_name}"
        return secret_name
    
    def _encrypt(self, secret: models.Secret) -> bytes:
        """Encrypt a Secret object using AES-GCM and return the encrypted bytes."""
        dek = secrets.token_bytes(32)
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(dek).encrypt(nonce, secret.model_dump_json().encode(), None)
        wrapped_dek = aes_key_wrap(base64.b64decode(os.environ["ORBITLAB_VAULT_KEY"]), dek)
        return base64.b64encode(json.dumps({
            "wrapped_dek": base64.b64encode(wrapped_dek).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
        }).encode())

    def _decrypt(self, blob: bytes | str) -> models.Secret:
        """Decrypt an encrypted blob using AES-GCM and return the plaintext string."""
        if isinstance(blob, str):
            blob = blob.encode()
        raw = json.loads(base64.b64decode(blob).decode())
        nonce = base64.b64decode(raw["nonce"])
        ciphertext = base64.b64decode(raw["ciphertext"])
        wrapped_dek = base64.b64decode(raw["wrapped_dek"])
        dek = aes_key_unwrap(base64.b64decode(os.environ["ORBITLAB_VAULT_KEY"]), wrapped_dek)
        return models.Secret.model_validate_json(AESGCM(dek).decrypt(nonce, ciphertext, None).decode())
    
    async def get_current_version(self, secret_name: str) -> int:
        name = self._get_name(secret_name=secret_name)
        if version := await self._get_decoded(name=name, key="current-version"):
            return int(version)
        raise exceptions.ResourceNotFoundError(name=name, key="current-version")
    
    async def create(self, secret_name: str, value: str, description: str = "") -> models.Secret:
        name = self._get_name(secret_name=secret_name)
        if await self.secret_exists(secret_name=secret_name):
            raise exceptions.ResourceAlreadyExistsError(name=name)
        secret = models.Secret.create(secret_name=secret_name, value=value, description=description)
        await self._hset(name=name, key=f"v{secret.secret_version}", value=self._encrypt(secret=secret))
        await self._hset(name=name, key="current-version", value=secret.secret_version)
        await self._set_add(self.INDEX, secret_name)
        return secret
    
    async def secret_exists(self, secret_name: str) -> bool:
        try:
            await self.get_current_version(secret_name=secret_name)
        except exceptions.ResourceNotFoundError:
            return False
        else:
            return True
    
    async def get(self, secret_name: str, version: int | None = None) -> models.Secret:
        if not version:
            version = await self.get_current_version(secret_name=secret_name)
        name = self._get_name(secret_name=secret_name)
        key = f"v{version}"
        if blob := await self._get_decoded(name=name, key=key):
            return self._decrypt(blob=blob)
        raise exceptions.ResourceNotFoundError(name=name, key=key)

    async def list_secrets(self, *, ignore_orbitlab_secrets: bool = True) -> list[models.Secret]:
        if ignore_orbitlab_secrets:
            return [
                await self.get(secret_name=secret_name)
                for secret_name in await self._list_set_members(index=self.INDEX) if not secret_name.startswith("/orbitlab/")
            ]
        return [
            await self.get(secret_name=secret_name)
            for secret_name in await self._list_set_members(index=self.INDEX)
        ]

    async def rotate(self, secret_name: str, version: int, new_value: str) -> models.Secret:
        secret: models.Secret = await self.get(secret_name=secret_name, version=version)
        secret.rotate(new_value=new_value)
        name = self._get_name(secret_name=secret.name)
        await self._hset(name=name, key=f"v{secret.secret_version}", value=self._encrypt(secret=secret))
        await self._hset(name=name, key="current-version", value=secret.secret_version)
        return secret

    async def rollback(self, secret_name: str) -> models.Secret:
        version = await self.get_current_version(secret_name=secret_name)
        secret = await self.get(secret_name=secret_name, version=version)
        if not secret.metadata.previous_versions:
            msg = f"No previous version of {secret_name} available for rollback."
            raise ValueError(msg)
        previous_version = max(*secret.metadata.previous_versions)
        name = self._get_name(secret_name=secret.name)
        await self._hset(name=name, key="current-version", value=previous_version)
        await self._hdel(name, f"v{secret.secret_version}")
        return await self.get(secret_name=secret_name, version=previous_version)

    async def delete(self, secret_name: str) -> None:
        await asyncio.gather(
            self.client.delete(self._get_name(secret_name=secret_name)),
            self._set_rem(self.INDEX, secret_name),
        )

    async def create_instance_password(self, instance_id: str, password: str = "") -> models.Secret:
        return await self.create(
            secret_name=f"/orbitlab/instance/{instance_id}",
            value=password or self.generate_random_password(),
            description=f"Password for {instance_id}",
        )

    async def get_instance_password(self, instance_id: str) -> str:
        secret = await self.get(secret_name=f"/orbitlab/instance/{instance_id}")
        return secret.secret_string.get_secret_value()

    async def delete_instance_password(self, instance_id: str) -> None:
        await self.delete(secret_name=f"/orbitlab/instance/{instance_id}")

    async def create_service_secret(self, service_name: str, service_id: str, *, value: str = "", subservice_name: str = "") -> models.Secret:
        secret_name = self._get_service_secret_name(service_name=service_name, service_id=service_id, subservice_name=subservice_name)
        return await self.create(
            secret_name=secret_name,
            value=value or self.generate_random_password(),
            description=f"{service_name} secret for {service_id}",
        )
    
    async def update_service_secret(self, service_name: str, service_id: str, value: str, subservice_name: str = "") -> models.Secret:
        secret_name = self._get_service_secret_name(service_name=service_name, service_id=service_id, subservice_name=subservice_name)
        version = await self.get_current_version(secret_name=secret_name)
        return await self.rotate(secret_name=secret_name, version=version, new_value=value)

    async def get_service_secret(self, service_name: str, service_id: str, *, subservice_name: str = "") -> str:
        secret_name = self._get_service_secret_name(service_name=service_name, service_id=service_id, subservice_name=subservice_name)
        secret = await self.get(secret_name=secret_name)
        return secret.secret_string.get_secret_value()

    async def delete_service_secret(self, service_name: str, service_id: str, *, subservice_name: str = "") -> None:
        secret_name = self._get_service_secret_name(service_name=service_name, service_id=service_id, subservice_name=subservice_name)
        await self.delete(secret_name=secret_name)

    async def store_private_key(self, cert_common_name: str, key_pem: str, *, ssh: bool = False) -> None:
        secret_name = f"/orbitlab/ssh/key/{cert_common_name}" if ssh else f"/orbitlab/pki/key/{cert_common_name}"
        name = f"{self.PKI_KEY_INDEX}:{secret_name}"
        if await self.secret_exists(secret_name=secret_name):
            raise exceptions.ResourceAlreadyExistsError(name=name)
        secret = models.Secret.create(
            secret_name=secret_name,
            value=key_pem,
            description=f"{cert_common_name} private key",
        )
        await self._hset(name=name, key=f"v{secret.secret_version}", value=self._encrypt(secret=secret))
        await self._hset(name=name, key="current-version", value=secret.secret_version)
        await self._set_add(self.PKI_KEY_INDEX, secret_name)

    async def get_private_key(self, cert_common_name: str, *, ssh: bool = False) -> str:
        secret_name = f"/orbitlab/ssh/key/{cert_common_name}" if ssh else f"/orbitlab/pki/key/{cert_common_name}"
        name = self._get_name(secret_name=secret_name)
        version = await self.get_current_version(secret_name=secret_name)
        key = f"v{version}"
        if data := await self._get_decoded(name=name, key=key):
            return models.Secret.model_validate_json(data).secret_string.get_secret_value()
        raise exceptions.ResourceNotFoundError(name=name, key=key)

    async def delete_private_key(self, cert_common_name: str, *, ssh: bool = False) -> None:
        secret_name = f"/orbitlab/ssh/key/{cert_common_name}" if ssh else f"/orbitlab/pki/key/{cert_common_name}"
        name = self._get_name(secret_name=secret_name)
        await self.client.delete(name)
        await self._set_rem(self.PKI_KEY_INDEX, secret_name)

    async def create_wardlink_keypair(self, sector: str, name: str) -> models.Secret:
        secret_name = f"/orbitlab/wardlink/{sector}/{name}/keys"
        name = self._get_name(secret_name=secret_name)
        if await self.secret_exists(secret_name=secret_name):
            raise exceptions.ResourceAlreadyExistsError(name=name)
        server_private, server_public = PKIClient.generate_wireguard_keypair()
        secret = models.Secret.create(
            secret_name=secret_name,
            value=json.dumps({"private": server_private, "public": server_public}),
            description=f"Sector {sector} WardLink client/server key pairs",
        )
        await self._hset(name=name, key=f"v{secret.secret_version}", value=self._encrypt(secret=secret))
        await self._hset(name=name, key="current-version", value=secret.secret_version)
        await self._set_add(self.PKI_KEY_INDEX, secret_name)
        return secret
    
    async def get_wardlink_keypair(self, sector: str, name: str) -> data_types.WardLinkKeyPair:
        secret_name = f"/orbitlab/wardlink/{sector}/{name}/keys"
        secret = await self.get(secret_name=secret_name)
        return json.loads(secret.secret_string.get_secret_value())

    @classmethod
    def generate_random_password(
        cls,
        length: int = 16,
        min_lower: int = 3,
        min_upper: int = 3,
        min_digits: int = 3,
    ) -> str:
        """Generate a random password with specified character requirements."""
        alphabet = string.ascii_letters + string.digits
        while True:
            password = "".join(secrets.choice(alphabet) for _ in range(length))
            if (
                sum(c.islower() for c in password) >= min_lower
                and sum(c.isupper() for c in password) >= min_upper
                and sum(c.isdigit() for c in password) >= min_digits
            ):
                break
        return password


class PKIClient(RedisClient):
    ROOT_CERTS_INDEX: Final = "ol:pki:root"
    INTERMEDIATE_CERTS_INDEX: Final = "ol:pki:intermediate"
    LEAF_CERTS_INDEX: Final = "ol:pki:leaf"
    
    RSA_PUBLIC_EXPONENT: Final = 65537
    RSA_KEY_SIZE: Final = 4096
    ROOT_CA_DAYS_VALID: Final = 20 * 365  # 356 days a year for 20 years
    INTERMEDIATE_CA_DAYS_VALID: Final = 5 * 365  # 356 days a year for 5 years
    LEAF_CA_DAYS_VALID: Final = 365  # 1 year

    def _get_name(self, index: str, common_name: str) -> str:
        return f"{index}:{common_name}"

    @classmethod
    def generate_wireguard_keypair(cls) -> tuple[str, str]:
        key = bytearray(os.urandom(32))
        key[0] &= 248
        key[31] &= 127
        key[31] |= 64
        private_raw = bytes(key)

        private_key = x25519.X25519PrivateKey.from_private_bytes(private_raw)
        public_key = private_key.public_key()

        public_raw = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        return (
            base64.b64encode(private_raw).decode(),
            base64.b64encode(public_raw).decode(),
        )

    async def create_certificate_authority(self, subject: models.Subject, key_usage: list[data_types.KeyUsageTypes]) -> models.RootCert:
        # Create self-signed certificate and output PEMs
        private_key = rsa.generate_private_key(
            public_exponent=self.RSA_PUBLIC_EXPONENT,
            key_size=self.RSA_KEY_SIZE,
        )
        subject_name = issuer_name = subject.to_x509()
        now = datetime.now(UTC)
        serial_number = secrets.randbits(128)
        not_before = now - timedelta(minutes=5)
        not_after = now + timedelta(days=self.ROOT_CA_DAYS_VALID)
        builder = (
            x509.CertificateBuilder()
            .serial_number(serial_number)
            .subject_name(subject_name)
            .issuer_name(issuer_name)
            .public_key(private_key.public_key())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(**data_types.KeyUsageTypes.to_x509_usage_params(key_usage)), critical=True)
        )
        cert = builder.sign(private_key=private_key, algorithm=hashes.SHA256())
        key_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        
        # Store Cert and Key data in Redis and add common name to set index
        certificate = models.RootCert(
            subject=subject,
            key_usage=key_usage,
            issuer=subject.common_name,
            not_before=not_before,
            not_after=not_after,
            certificate=cert_pem,
            fingerprint=f"SHA256:{hashlib.sha256(cert_pem.encode()).hexdigest()}",
            serial_number=str(serial_number),
        )
        name = self._get_name(index=self.ROOT_CERTS_INDEX, common_name=subject.common_name)
        await self.client.set(name=name, value=certificate.model_dump_json())
        await SecretsClient().store_private_key(cert_common_name=subject.common_name, key_pem=key_pem)
        await self._set_add(self.ROOT_CERTS_INDEX, subject.common_name)
        return certificate

    async def list_root_certificates(self) -> list[models.RootCert]:
        return [
            await self.get_root_certificate(common_name=common_name)
            for common_name in await self._list_set_members(index=self.ROOT_CERTS_INDEX)
        ]

    async def get_root_certificate(self, common_name: str) -> models.RootCert:
        name = self._get_name(index=self.ROOT_CERTS_INDEX, common_name=common_name)
        if data := await self.client.get(name=name):
            return models.RootCert.model_validate_json(data)
        raise exceptions.ResourceNotFoundError(name=name)

    async def delete_root_certificate(self, common_name: str) -> None:
        name = self._get_name(index=self.ROOT_CERTS_INDEX, common_name=common_name)
        await self.client.delete(name)
        await self._set_rem(self.ROOT_CERTS_INDEX, common_name)

    async def create_intermediate_certificate(self, common_name: str, root_ca_common_name: str, domain_constraint: str) -> models.IntermediateCert:
        """Create a new intermediate certificate signed by the specified root CA."""
        root = await self.get_root_certificate(common_name=root_ca_common_name)
        root_key = serialization.load_pem_private_key(
            (await SecretsClient().get_private_key(cert_common_name=root_ca_common_name)).encode(),
            password=None,
        )
        root_key = cast("rsa.RSAPrivateKey", root_key)
        
        root_cert = x509.load_pem_x509_certificate(root.certificate.encode())

        private_key = rsa.generate_private_key(
            public_exponent=self.RSA_PUBLIC_EXPONENT,
            key_size=self.RSA_KEY_SIZE,
        )
        now = datetime.now(UTC)
        serial_number = secrets.randbits(128)
        not_before = now - timedelta(minutes=5)
        not_after = now + timedelta(days=self.INTERMEDIATE_CA_DAYS_VALID)
        intermediate_subject = root.subject.model_copy()
        intermediate_subject.common_name = common_name

        builder = (
            x509.CertificateBuilder()
            .serial_number(serial_number)
            .subject_name(intermediate_subject.to_x509())
            .issuer_name(root_cert.subject)
            .public_key(private_key.public_key())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(**data_types.KeyUsageTypes.to_x509_usage_params(root.key_usage)),
                critical=True,
            )
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()), critical=False)
            .add_extension(
                x509.NameConstraints(
                    permitted_subtrees=[x509.DNSName(domain_constraint)],
                    excluded_subtrees=None,
                ),
                critical=True,
            )
        )
        cert = builder.sign(private_key=root_key, algorithm=hashes.SHA256())

        key_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()

        certificate = models.IntermediateCert(
            subject=intermediate_subject,
            key_usage=root.key_usage,
            issuer=root.subject.common_name,
            not_before=not_before,
            not_after=not_after,
            certificate=cert_pem,
            fingerprint=f"SHA256:{hashlib.sha256(cert_pem.encode()).hexdigest()}",
            serial_number=str(serial_number),
            domain_constraint=domain_constraint,
            chain=root_cert.public_bytes(serialization.Encoding.PEM).decode()
        )
        name = self._get_name(index=self.INTERMEDIATE_CERTS_INDEX, common_name=intermediate_subject.common_name)
        await self.client.set(name=name, value=certificate.model_dump_json())
        await SecretsClient().store_private_key(cert_common_name=intermediate_subject.common_name, key_pem=key_pem)
        await self._set_add(self.INTERMEDIATE_CERTS_INDEX, intermediate_subject.common_name)
        return certificate

    async def get_intermediate_certificate(self, common_name: str) -> models.IntermediateCert:
        name = self._get_name(index=self.INTERMEDIATE_CERTS_INDEX, common_name=common_name)
        if data := await self.client.get(name=name):
            return models.IntermediateCert.model_validate_json(data)
        raise exceptions.ResourceNotFoundError(name=name)

    async def list_intermediate_certificates(self) -> list[models.IntermediateCert]:
        return [
            await self.get_intermediate_certificate(common_name=common_name)
            for common_name in await self._list_set_members(index=self.INTERMEDIATE_CERTS_INDEX)
        ]

    async def delete_intermediate_certificate(self, common_name: str) -> None:
        name = self._get_name(index=self.INTERMEDIATE_CERTS_INDEX, common_name=common_name)
        await self.client.delete(name)
        await self._set_rem(self.INTERMEDIATE_CERTS_INDEX, common_name)

    async def create_leaf_certificate(self, common_name: str, san_dns: list[str], san_ips: list[str], signing_ca_common_name: str, *, server_auth: bool) -> models.LeafCert:
        signer = await self.get_intermediate_certificate(common_name=signing_ca_common_name)
        
        
        private_key = rsa.generate_private_key(
            public_exponent=self.RSA_PUBLIC_EXPONENT,
            key_size=self.RSA_KEY_SIZE,
        )
        key_usage = [data_types.KeyUsageTypes.DIGITAL_SIGNATURE, data_types.KeyUsageTypes.KEY_AGREEMENT]
        if server_auth:
            key_usage.append(data_types.KeyUsageTypes.KEY_ENCIPHERMENT)

        leaf_subject = signer.subject.model_copy()
        leaf_subject.common_name = common_name

        builder = x509.CertificateSigningRequestBuilder().subject_name(leaf_subject.to_x509())
        if san_dns or san_ips:
            general_names: list[x509.DNSName | x509.IPAddress] = [x509.DNSName(value=name) for name in san_dns]
            general_names.extend([x509.IPAddress(value=ip_address(address=address)) for address in san_ips])
            builder = builder.add_extension(x509.SubjectAlternativeName(general_names=general_names), critical=False)
        csr: x509.CertificateSigningRequest = builder.sign(private_key=private_key, algorithm=hashes.SHA256())
        cert_pem = await self.sign_csr(csr.public_bytes(serialization.Encoding.PEM).decode(), signing_ca_common_name=signing_ca_common_name)
        signed_leaf = x509.load_pem_x509_certificate(cert_pem.encode())
        key_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        
        certificate = models.LeafCert(
            subject=leaf_subject,
            key_usage=key_usage,
            issuer=signer.subject.common_name,
            not_before=signed_leaf.not_valid_before_utc,
            not_after=signed_leaf.not_valid_after_utc,
            certificate=cert_pem,
            fingerprint=f"SHA256:{hashlib.sha256(cert_pem.encode()).hexdigest()}",
            serial_number=str(signed_leaf.serial_number),
            chain=x509.load_pem_x509_certificate(signer.certificate.encode()).public_bytes(serialization.Encoding.PEM).decode(),
            san_dns=san_dns,
            san_ips=san_ips,
        )

        name = self._get_name(index=self.LEAF_CERTS_INDEX, common_name=leaf_subject.common_name)
        await self.client.set(name=name, value=certificate.model_dump_json())
        await SecretsClient().store_private_key(cert_common_name=leaf_subject.common_name, key_pem=key_pem)
        await self._set_add(self.LEAF_CERTS_INDEX, leaf_subject.common_name)
        return certificate

    async def sign_csr(self, csr_der: str, signing_ca_common_name: str) -> str:
        signer = await self.get_intermediate_certificate(common_name=signing_ca_common_name)
        csr = x509.load_pem_x509_csr(csr_der.encode())
        signing_key = serialization.load_pem_private_key(
            (await SecretsClient().get_private_key(cert_common_name=signing_ca_common_name)).encode(),
            password=None,
        )
        signing_key = cast("rsa.RSAPrivateKey", signing_key)
        signing_cert = x509.load_pem_x509_certificate(signer.certificate.encode())

        now = datetime.now(UTC)
        serial_number = secrets.randbits(128)
        not_before = now - timedelta(minutes=5)
        not_after = now + timedelta(days=self.LEAF_CA_DAYS_VALID)

        builder = (
            x509.CertificateBuilder()
            .serial_number(serial_number)
            .subject_name(csr.subject)
            .issuer_name(signing_cert.subject)
            .public_key(csr.public_key())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        )
        for extension in csr.extensions._extensions:
            builder = builder.add_extension(extension.value, critical=extension.critical)

        cert = builder.sign(private_key=signing_key, algorithm=hashes.SHA256())
        return cert.public_bytes(serialization.Encoding.PEM).decode()

    async def get_leaf_certificate(self, common_name: str) -> models.LeafCert:
        name = self._get_name(index=self.LEAF_CERTS_INDEX, common_name=common_name)
        if data := await self.client.get(name=name):
            return models.LeafCert.model_validate_json(data)
        raise exceptions.ResourceNotFoundError(name=name)

    async def list_leaf_certificates(self) -> list[models.LeafCert]:
        return [
            await self.get_leaf_certificate(common_name=common_name)
            for common_name in await self._list_set_members(index=self.LEAF_CERTS_INDEX)
        ]

    async def delete_leaf_certificate(self, common_name: str) -> None:
        name = self._get_name(index=self.LEAF_CERTS_INDEX, common_name=common_name)
        await self.client.delete(name)
        await self._set_rem(self.LEAF_CERTS_INDEX, common_name)


class SSHKeyClient(PKIClient):
    INDEX: Final = "ol:pki:root"
    
    def _get_name(self, key_pair_name: str) -> str:
        return f"ol:sshkey:{key_pair_name}"
    
    async def list_key_pairs(self) -> list[models.SSHKey]:
        return [
            await self.get_key_pair(key_pair_name=key_pair_name)
            for key_pair_name in await self._list_set_members(index=self.INDEX)
        ]
    
    async def key_pair_exists(self, key_pair_name: str) -> bool:
        return key_pair_name in await self._list_set_members(index=self.INDEX)
    
    async def create_key_pair(self, key_pair_name: str, key_type: data_types.SSHKeyTypes) -> models.SSHKey:
        name = self._get_name(key_pair_name=key_pair_name)
        if await self.key_pair_exists(key_pair_name=key_pair_name):
            raise exceptions.ResourceAlreadyExistsError(name=name)

        if key_type == data_types.SSHKeyTypes.ED25519:
            private_key = ed25519.Ed25519PrivateKey.generate()
        else:
            private_key = rsa.generate_private_key(
                public_exponent=self.RSA_PUBLIC_EXPONENT,
                key_size=self.RSA_KEY_SIZE,
                backend=default_backend(),
            )

        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        ).decode()

        ssh_key = models.SSHKey(
            key_type=key_type,
            public_key=public_key,
            fingerprint=f"SHA256:{hashlib.sha256(public_key.encode()).hexdigest()}",
        )
        
        await self.client.set(name=name, value=ssh_key.model_dump_json())
        await SecretsClient().store_private_key(cert_common_name=key_pair_name, key_pem=private_key_pem, ssh=True)
        await self._set_add(self.INDEX, key_pair_name)
        return ssh_key

    async def get_key_pair(self, key_pair_name: str) -> models.SSHKey:
        if not await self.key_pair_exists(key_pair_name=key_pair_name):
            raise exceptions.ResourceNotFoundError(name=self._get_name(key_pair_name=key_pair_name))
        data = await self.client.get(name=self._get_name(key_pair_name=key_pair_name))
        return models.SSHKey.model_validate_json(data)

    async def get_private_key(self, key_pair_name: str) -> str:
        if not await self.key_pair_exists(key_pair_name=key_pair_name):
            raise exceptions.ResourceNotFoundError(name=self._get_name(key_pair_name=key_pair_name))
        return await SecretsClient().get_private_key(cert_common_name=key_pair_name, ssh=True)     

    async def delete_key_pair(self, key_pair_name: str) -> None:
        await self.client.delete(self._get_name(key_pair_name=key_pair_name))
        await self._set_rem(self.INDEX, key_pair_name)
        await SecretsClient().delete_private_key(cert_common_name=key_pair_name, ssh=True)


class ApplianceClient(RedisClient):
    BASE_APPLIANCE_INDEX: Final = "ol:appliances:base"
    CUSTOM_APPLIANCE_INDEX: Final = "ol:appliances:custom"
    
    def _appliance_name(self, id: str, index: str) -> str:
        return f"{index}:{id}"

    async def generate_appliance_id(self, appliance_type: Literal["base", "custom"]) -> str:
        index = self.BASE_APPLIANCE_INDEX if appliance_type == "base" else self.CUSTOM_APPLIANCE_INDEX
        return await self._generate_unique_id(prefix="oli", index=index)

    async def appliance_exists(self, appliance_type: Literal["base", "custom"], id: str) -> bool:
        index = self.BASE_APPLIANCE_INDEX if appliance_type == "base" else self.CUSTOM_APPLIANCE_INDEX
        return id in await self._list_set_members(index=index)

    @overload
    async def set_appliance(self, appliance_type: Literal["base"], config: models.BaseApplianceConfig) -> None: ...

    @overload
    async def set_appliance(self, appliance_type: Literal["custom"], config: models.CustomApplianceConfig) -> None: ...

    async def set_appliance(self, appliance_type: Literal["base", "custom"], config: models.BaseApplianceConfig | models.CustomApplianceConfig) -> None:
        index = self.BASE_APPLIANCE_INDEX if appliance_type == "base" else self.CUSTOM_APPLIANCE_INDEX
        name = self._appliance_name(id=config.id, index=index)
        await self._mutate_object(name=name, submitted=config)
        await self._set_add(index, config.id)
    
    @overload
    async def get_appliance(self, appliance_type: Literal["base"], id: str) -> models.BaseAppliance: ...

    @overload
    async def get_appliance(self, appliance_type: Literal["custom"], id: str) -> models.CustomAppliance: ...
    
    async def get_appliance(self, appliance_type: Literal["base", "custom"], id: str) -> models.BaseAppliance | models.CustomAppliance:
        if appliance_type == "base":
            name = self._appliance_name(id=id, index=self.BASE_APPLIANCE_INDEX)
            if config := await self._get_config(name=name, model=models.BaseApplianceConfig):
                state = await self._get_state(name=name, model=models.BaseApplianceState)
                return models.BaseAppliance(config=config, state=state)
        else:
            name = self._appliance_name(id=id, index=self.CUSTOM_APPLIANCE_INDEX)
            if config := await self._get_config(name=name, model=models.CustomApplianceConfig):
                state = await self._get_state(name=name, model=models.CustomApplianceState)
                return models.CustomAppliance(config=config, state=state)
            
        raise exceptions.ResourceNotFoundError(name=name)

    @overload
    async def list_appliances(self, appliance_type: Literal["base"]) -> Sequence[models.BaseAppliance]: ...

    @overload
    async def list_appliances(self, appliance_type: Literal["custom"]) -> Sequence[models.CustomAppliance]: ...

    async def list_appliances(self, appliance_type: Literal["base", "custom"]) -> Sequence[models.BaseAppliance | models.CustomAppliance]:
        index = self.BASE_APPLIANCE_INDEX if appliance_type == "base" else self.CUSTOM_APPLIANCE_INDEX
        return [await self.get_appliance(appliance_type=appliance_type, id=id) for id in await self._list_set_members(index=index)]

    async def delete_appliance(self, appliance_type: Literal["base", "custom"], id: str) -> None:
        index = self.BASE_APPLIANCE_INDEX if appliance_type == "base" else self.CUSTOM_APPLIANCE_INDEX
        await asyncio.gather(
            self.client.delete(self._appliance_name(id=id, index=index)),
            self._set_rem(index, id),
        )

    async def set_appliance_downloaded(self, id: str, volume_id: str) -> None:
        name = self._appliance_name(id=id, index=self.BASE_APPLIANCE_INDEX)
        await asyncio.gather(
            self._hset(name=name, key="volume_id", value=volume_id),
            self._hset(name=name, key="download_date", value=datetime.now(UTC).isoformat())
        )
    
    async def set_workflow_status(self, id: str, workflow_status: data_types.TemplateWorkflowStatus) -> None:
        name = self._appliance_name(id=id, index=self.CUSTOM_APPLIANCE_INDEX)
        await self._hset(name=name, key="workflow_status", value=str(workflow_status))
        if workflow_status == data_types.TemplateWorkflowStatus.PENDING:
            await self._hset(name=name, key="last_execution", value=datetime.now(UTC).isoformat())

    async def get_workflow_status(self, id: str) -> data_types.TemplateWorkflowStatus:
        name = self._appliance_name(id=id, index=self.CUSTOM_APPLIANCE_INDEX)
        if status := await self._get_decoded(name=name, key="workflow_status"):
            return data_types.TemplateWorkflowStatus(status)
        return data_types.TemplateWorkflowStatus.NEVER_RAN

    async def update_workflow_logs(self, id: str, logs: list[str], *, reset: bool = False) -> None:
        name = self._appliance_name(id=id, index=self.CUSTOM_APPLIANCE_INDEX)
        log_lines = "\n".join(logs)
        if reset:
            await self._hset(name=name, key="workflow_logs", value=log_lines)
        else:
            previous_logs = await self._get_decoded(name=name, key="workflow_logs")
            new_logs = f"{previous_logs}\n{log_lines}" if previous_logs else log_lines
            await self._hset(name=name, key="workflow_logs", value=new_logs)

    async def get_workflow_logs(self, id: str) -> str:
        name = self._appliance_name(id=id, index=self.CUSTOM_APPLIANCE_INDEX)
        if logs := await self._get_decoded(name=name, key="workflow_logs"):
            return logs
        return ""

    async def workflow_succeeded(self, id: str, volume_id: str) -> None:
        name = self._appliance_name(id=id, index=self.CUSTOM_APPLIANCE_INDEX)
        await self._hset(name=name, key="workflow_status", value=str(data_types.TemplateWorkflowStatus.SUCCEEDED))
        await self._hset(name=name, key="volume_id", value=volume_id)

    async def get_volume_id(self, id: str) -> str:
        if await self.appliance_exists(appliance_type="base", id=id):
            name = self._appliance_name(id=id, index=self.BASE_APPLIANCE_INDEX)
            state = await self._get_state(name=name, model=models.BaseApplianceState)
            return state.volume_id
        name = self._appliance_name(id=id, index=self.CUSTOM_APPLIANCE_INDEX)
        state = await self._get_state(name=name, model=models.CustomApplianceState)
        return state.volume_id


class ImagesClient(RedisClient):
    BASE_IMAGE_INDEX: Final = "ol:images:base"
    CUSTOM_IMAGE_INDEX: Final = "ol:images:custom"
    
    def _image_name(self, id: str, index: str) -> str:
        return f"{index}:{id}"
    
    async def generate_image_id(self, image_type: Literal["base", "custom"]) -> str:
        index = self.BASE_IMAGE_INDEX if image_type == "base" else self.CUSTOM_IMAGE_INDEX
        return await self._generate_unique_id(prefix="ovi", index=index)

    async def image_exists(self, image_type: Literal["base", "custom"], id: str) -> bool:
        index = self.BASE_IMAGE_INDEX if image_type == "base" else self.CUSTOM_IMAGE_INDEX
        return id in await self._list_set_members(index=index)

    @overload
    async def set_image(self, image_type: Literal["base"], config: models.BaseImageConfig) -> None: ...

    @overload
    async def set_image(self, image_type: Literal["custom"], config: models.CustomImageConfig) -> None: ...

    async def set_image(self, image_type: Literal["base", "custom"], config: models.BaseImageConfig | models.CustomImageConfig) -> None:
        index = self.BASE_IMAGE_INDEX if image_type == "base" else self.CUSTOM_IMAGE_INDEX
        name = self._image_name(id=config.id, index=index)
        await self._mutate_object(name=name, submitted=config)
        await self._set_add(index, config.id)
    
    @overload
    async def get_image(self, image_type: Literal["base"], id: str) -> models.BaseImage: ...

    @overload
    async def get_image(self, image_type: Literal["custom"], id: str) -> models.CustomImage: ...
    
    async def get_image(self, image_type: Literal["base", "custom"], id: str) -> models.BaseImage | models.CustomImage:
        if image_type == "base":
            name = self._image_name(id=id, index=self.BASE_IMAGE_INDEX)
            if config := await self._get_config(name=name, model=models.BaseImageConfig):
                state = await self._get_state(name=name, model=models.BaseImageState)
                return models.BaseImage(config=config, state=state)
        else:
            name = self._image_name(id=id, index=self.CUSTOM_IMAGE_INDEX)
            if config := await self._get_config(name=name, model=models.CustomImageConfig):
                state = await self._get_state(name=name, model=models.CustomImageState)
                return models.CustomImage(config=config, state=state)
        
        raise exceptions.ResourceNotFoundError(name=name)

    @overload
    async def list_images(self, image_type: Literal["base"]) -> Sequence[models.BaseImage]: ...

    @overload
    async def list_images(self, image_type: Literal["custom"]) -> Sequence[models.CustomImage]: ...

    async def list_images(self, image_type: Literal["base", "custom"]) -> Sequence[models.BaseImage | models.CustomImage]:
        index = self.BASE_IMAGE_INDEX if image_type == "base" else self.CUSTOM_IMAGE_INDEX
        return [await self.get_image(image_type=image_type, id=id) for id in await self._list_set_members(index=index)]

    async def set_base_image_downloaded(self, id: str, volume_id: str) -> None:
        name = self._image_name(id=id, index=self.BASE_IMAGE_INDEX)
        await self._hset(name=name, key="volume_id", value=volume_id)
        await self._hset(name=name, key="download_date", value=datetime.now(UTC).isoformat())

    async def delete_image(self, image_type: Literal["base", "custom"], id: str) -> None:
        index = self.BASE_IMAGE_INDEX if image_type == "base" else self.CUSTOM_IMAGE_INDEX
        await self.client.delete(self._image_name(id=id, index=index))
        await self._set_rem(index, id)

    async def set_workflow_status(self, id: str, workflow_status: data_types.TemplateWorkflowStatus) -> None:
        name = self._image_name(id=id, index=self.CUSTOM_IMAGE_INDEX)
        await self._hset(name=name, key="workflow_status", value=str(workflow_status))
        if workflow_status == data_types.TemplateWorkflowStatus.PENDING:
            await self._hset(name=name, key="last_execution", value=datetime.now(UTC).isoformat())

    async def get_workflow_status(self, id: str) -> data_types.TemplateWorkflowStatus:
        name = self._image_name(id=id, index=self.CUSTOM_IMAGE_INDEX)
        if status := await self._get_decoded(name=name, key="workflow_status"):
            return data_types.TemplateWorkflowStatus(status)
        return data_types.TemplateWorkflowStatus.NEVER_RAN

    async def update_workflow_logs(self, id: str, logs: list[str], *, reset: bool = False) -> None:
        name = self._image_name(id=id, index=self.CUSTOM_IMAGE_INDEX)
        log_lines = "\n".join(logs)
        if reset:
            await self._hset(name=name, key="workflow_logs", value=log_lines)
        else:
            previous_logs = await self._get_decoded(name=name, key="workflow_logs")
            new_logs = f"{previous_logs}\n{log_lines}" if previous_logs else log_lines
            await self._hset(name=name, key="workflow_logs", value=new_logs)

    async def get_workflow_logs(self, id: str) -> str:
        name = self._image_name(id=id, index=self.CUSTOM_IMAGE_INDEX)
        if logs := await self._get_decoded(name=name, key="workflow_logs"):
            return logs
        return ""

    async def workflow_succeeded(self, id: str, volume_id: str) -> None:
        name = self._image_name(id=id, index=self.CUSTOM_IMAGE_INDEX)
        await self._hset(name=name, key="workflow_status", value=str(data_types.TemplateWorkflowStatus.SUCCEEDED))
        await self._hset(name=name, key="volume_id", value=volume_id)

    async def get_volume_id(self, id: str) -> str:
        if await self.image_exists(image_type="base", id=id):
            name = self._image_name(id=id, index=self.BASE_IMAGE_INDEX)
            state = await self._get_state(name=name, model=models.BaseImageState)
            return state.volume_id
        name = self._image_name(id=id, index=self.CUSTOM_IMAGE_INDEX)
        state = await self._get_state(name=name, model=models.CustomImageState)
        return state.volume_id


class InstanceClient(RedisClient):
    INSTANCE_INDEX: Final = "ol:instances"
    MAC_INDEX: Final = "ol:instances:macs"

    def _instance_name(self, id: str) -> str:
        return f"{self.INSTANCE_INDEX}:{id}"
    
    async def generate_instance_id(self) -> str:
        return await self._generate_unique_id(prefix="i", index=self.INSTANCE_INDEX, count=16)

    async def instance_exists(self, id: str) -> bool:
        return id in await self._list_set_members(index=self.INSTANCE_INDEX)
    
    async def set_instance(self, config: models.InstanceConfig) -> None:
        name = self._instance_name(id=config.id)
        await self._mutate_object(name=name, submitted=config)
        await self._set_add(self.INSTANCE_INDEX, config.id)
        await self._hset(name=self.MAC_INDEX, key=config.mac, value=config.id)

    async def set_instance_vmid(self, id: str, vmid: int) -> None:
        name = self._instance_name(id=id)
        await self._hset(name=name, key="vmid", value=vmid)
        
    async def set_instance_status(self, id: str, status: data_types.ComputeStatus) -> None:
        name = self._instance_name(id=id)
        await self._hset(name=name, key="status", value=str(status))
    
    async def set_instance_address(self, id: str, address: IPv4Interface) -> None:
        name = self._instance_name(id=id)
        await self._hset(name=name, key="address", value=str(address))

    async def get_instance(self, id: str) -> models.Instance:
        name = self._instance_name(id=id)
        if config := await self._get_config(name=name, model=models.InstanceConfig):
            state = await self._get_state(name=name, model=models.InstanceState)
            return models.Instance(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name)

    async def get_instance_by_mac(self, mac: str) -> models.Instance | None:
        if id := await self._get_decoded(self.MAC_INDEX, key=mac):
            return await self.get_instance(id=id)
        return None

    async def list_instances(self) -> list[models.Instance]:
        return [
            await self.get_instance(id=id) for id in await self._list_set_members(index=self.INSTANCE_INDEX)
        ]

    async def generate_create_params(self, vmid: int, id: str) -> dict:
        name = self._instance_name(id=id)
        if config := await self._get_config(name=name, model=models.InstanceConfig):
            sector = await SectorClient().get(id=config.sector)
            password = await SecretsClient().get_instance_password(instance_id=id)
            params = {
                "cores": config.cores,
                "memory": config.memory * 1024,
                "vmid": vmid,
                "searchdomain": "sector.internal",
                "nameserver": str(sector.config.dns_address.ip),
                "onboot": "1",
            }
            if config.type == "lxc":
                params.update({
                    "features": config.features,
                    "ostemplate": config.volume_id,
                    "hostname": config.name,
                    "swap": config.memory * 1024,
                    "net0": f"name=eth0,hwaddr={config.mac},bridge={config.sector},ip=dhcp",
                    "rootfs": f"{config.storage}:{config.disk_size}",
                    "unprivileged": "0" if config.nfs else "1",
                    "password": password,
                })
            else:
                params.update({
                "name": config.name,
                "sockets": config.sockets,
                "cpu": "x86-64-v2-AES",
                "numa": 0,
                "agent": "enabled=1",
                "serial0": "socket",
                "scsi0": f"{config.storage}:0,import-from={config.volume_id}",
                "ide0": f"{config.storage}:cloudinit",
                "citype": "nocloud",
                "ciuser": config.user,
                "cipassword": password,
                "ciupgrade": "0",
                "net0": f"virtio,macaddr={config.mac},bridge={config.sector}",
                "ipconfig0": "ip=dhcp",
                "scsihw": "virtio-scsi-single",
                "ostype": "l26",
                "boot": "order=scsi0",
            })
            return params
        raise exceptions.ResourceNotFoundError(name=name)

    async def delete_instance(self, id: str) -> None:
        name = self._instance_name(id=id)
        cleanup_tasks = [
            self.client.delete(name),
            SecretsClient().delete_instance_password(instance_id=id),
            self._set_rem(self.INSTANCE_INDEX, id),
        ]
        if config := await self._get_config(name=name, model=models.InstanceConfig):
            cleanup_tasks.append(self._hdel(self.MAC_INDEX, config.mac))
        await asyncio.gather(*cleanup_tasks)


class DataCoreClient(RedisClient):
    INDEX: Final = "ol:datacore:clusters"

    def _cluster_name(self, id: str) -> str:
        return f"{self.INDEX}:{id}"

    async def generate_cluster_id(self) -> str:
        return await self._generate_unique_id(prefix="dcc", index=self.INDEX)

    async def datacore_exists(self, id: str) -> bool:
        return id in await self._list_set_members(index=self.INDEX)

    async def set_datacore(self, config: models.DataCoreConfig) -> None:
        name = self._cluster_name(id=config.id)
        await self._mutate_object(name=name, submitted=config)
        await self._set_add(self.INDEX, config.id)

    async def get_datacore(self, id: str) -> models.DataCore:
        name = self._cluster_name(id=id)
        if config := await self._get_config(name=name, model=models.DataCoreConfig):
            state = await self._get_state(name=name, model=models.DataCoreState)
            return models.DataCore(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name)

    async def list_datacores(self) -> list[models.DataCore]:
        return [
            await self.get_datacore(id=id) for id in await self._list_set_members(index=self.INDEX)
        ]
    
    async def _mutate_nodes(self, id: str, node: models.DataCoreNode, *, remove: bool = False) -> None:
        name = self._cluster_name(id=id)
        if data := await self._get_decoded(name=name, key="nodes"):
            nodes = models.DataCoreNodes.model_validate_json(data)
        else:
            nodes = models.DataCoreNodes(root=[])
        
        if remove:
            nodes.root.remove(node)
        else:
            nodes.root.append(node)
        await self._hset(name=name, key="nodes", value=nodes.model_dump_json())
    
    async def remove_node(self, id: str, node: models.DataCoreNode) -> None:
        await self._mutate_nodes(id=id, node=node, remove=True)

    async def update_nodes(self, id: str, nodes: models.DataCoreNodes) -> None:
        name = self._cluster_name(id=id)
        await self._hset(name=name, key="nodes", value=nodes.model_dump_json())
        if nodes.healthy:
            await self._hset(name=name, key="status", value=str(data_types.DataCoreStatus.AVAILABLE))
        elif nodes.degraded:
            await self._hset(name=name, key="status", value=str(data_types.DataCoreStatus.DEGRADED))
        else:
            await self._hset(name=name, key="status", value=str(data_types.DataCoreStatus.UNHEALTHY))

    async def set_node_role(self, id: str, name: str, role: str) -> None:
        name = self._cluster_name(id=id)
        if data := await self._get_decoded(name=name, key="nodes"):
            nodes = models.DataCoreNodes.model_validate_json(data)
            for node in nodes.root:
                if node.name == name:
                    node.role = role
            await self._hset(name=name, key="nodes", value=nodes.model_dump_json())

    async def set_cluster_status(self, id: str, status: data_types.DataCoreStatus) -> None:
        await self._hset(name=self._cluster_name(id=id), key="status", value=str(status))

    async def generate_cluster_config(self, id: str) -> dict:
        name = self._cluster_name(id=id)
        if config := await self._get_config(name=name, model=models.DataCoreConfig):
            secret_client = SecretsClient()
            return {
                "rw_virtual_router_id": config.rw_virtual_router_id,
                "ro_virtual_router_id": config.ro_virtual_router_id,
                "rw_vip": str(config.rw_vip),
                "ro_vip": str(config.ro_vip),
                "keepalived_password": secret_client.generate_random_password(),
                "superuser_password": await secret_client.get_service_secret(service_name="datacore", service_id=id, subservice_name="superuser"),
                "replication_password": await secret_client.get_service_secret(service_name="datacore", service_id=id, subservice_name="replication"),
            }
        raise exceptions.ResourceNotFoundError(name=name)

    async def generate_node_params(self, id: str, vmid: int) -> dict:
        name = self._cluster_name(id=id)
        if config := await self._get_config(name=name, model=models.DataCoreConfig):
            state = await self._get_state(name=name, model=models.DataCoreState)
            sector = await SectorClient().get(id=config.sector)
            infra = await ClusterClient().get_infra_appliances()
            node = models.DataCoreNode(
                vmid=vmid,
                name=await self._generate_unique_id(prefix=config.id, count=6, existing=[node.name for node in state.nodes.root]),
            )
            await self._mutate_nodes(id=id, node=node) # Adds the node to the index
            return {
                "pool": config.id,
                "features": "nesting=1",
                "ostemplate": infra.appliances["datacore"].volume_id,
                "hostname": node.name,
                "cores": config.cores,
                "memory": config.memory_gb * 1024,
                "swap": 512,
                "net0": f"name=eth0,bridge={config.sector},ip=dhcp,mtu=1450",
                "rootfs": f"{config.storage}:{config.capacity_gb}",
                "unprivileged": "1",
                "vmid": vmid,
                "password": SecretsClient.generate_random_password(),
                "searchdomain": "sector.internal",
                "nameserver": str(sector.config.dns_address.ip),
                "onboot": "1",
            }
        raise exceptions.ResourceNotFoundError(name=name)

    async def delete(self, id: str) -> None:
        name = self._cluster_name(id=id)
        if config := await self._get_config(name=name, model=models.DataCoreConfig):
            secret_client = SecretsClient()
            await asyncio.gather(
                secret_client.delete_service_secret(service_name="datacore", service_id=id, subservice_name="superuser"),
                secret_client.delete_service_secret(service_name="datacore", service_id=id, subservice_name="replication"),
                self.client.delete(name),
                self._set_rem(self.INDEX, config.id),
            )


class DockFSClient(RedisClient):
    INDEX: Final = "ol:dockfs:clusters"
    MAC_INDEX: Final = "ol:dockfs:macs"

    def _cluster_name(self, id: str) -> str:
        return f"{self.INDEX}:{id}"

    async def generate_cluster_id(self) -> str:
        return await self._generate_unique_id(prefix="dfs", index=self.INDEX)

    async def cluster_exists(self, id: str) -> bool:
        return id in await self._list_set_members(index=self.INDEX)

    async def set_dockfs(self, config: models.DockFSConfig) -> None:
        name = self._cluster_name(id=config.id)
        await self._mutate_object(name=name, submitted=config)
        await self._set_add(self.INDEX, config.id)

    async def get_dockfs(self, id: str) -> models.DockFS:
        name = self._cluster_name(id=id)
        if config := await self._get_config(name=name, model=models.DockFSConfig):
            state = await self._get_state(name=name, model=models.DockFSState)
            return models.DockFS(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name)

    async def get_cluster_id_by_mac(self, mac: str) -> str | None:
        if cluster_id := await self._get_decoded(name=self.MAC_INDEX, key=mac):
            return cluster_id
        return None

    async def list_dockfs_clusters(self) -> list[models.DockFS]:
        return [
            await self.get_dockfs(id=id) for id in await self._list_set_members(index=self.INDEX)
        ]

    async def generate_node_params(self, id: str, vmid: int, node_type: Literal["active", "passive"]) -> tuple[str, dict]:
        name = self._cluster_name(id=id)
        if config := await self._get_config(name=name, model=models.DockFSConfig):
            state = await self._get_state(name=name, model=models.DockFSState)
            
            hostname = await self._generate_unique_id(prefix=config.id, count=6, existing=state.node_names)
            macaddr = models.DockFSConfig.generate_mac(hostname=hostname)
            await self._hset(name=self.MAC_INDEX, key=macaddr, value=config.id)
            sector = await SectorClient().get(id=config.sector)
            infra = await ClusterClient().get_infra_appliances()
            
            params = {
                "vmid": vmid,
                "name": hostname,
                "cores": config.cores,
                "sockets": config.sockets,
                "memory": config.memory * 1024,
                "cpu": "x86-64-v2-AES",
                "numa": 0,
                "agent": "enabled=1",
                "serial0": "socket",
                "scsi0": f"{config.storage}:0,import-from={infra.appliances['dockfs'].volume_id}",
                "ide0": f"{config.storage}:cloudinit",
                "citype": "nocloud",
                "ciuser": "root",
                "cipassword": SecretsClient.generate_random_password(),
                "net0": f"virtio,macaddr={macaddr},bridge={config.sector}",
                "ipconfig0": "ip=dhcp",
                "searchdomain": "sector.internal",
                "nameserver": str(sector.config.dns_address.ip),
                "scsihw": "virtio-scsi-single",
                "ostype": "l26",
                "onboot": "1",
                "boot": "order=scsi0",
            }
            if node_type == "active":
                params["scsi1"] = f"{config.storage}:{config.capacity_gb}"
            return macaddr, params
        raise exceptions.ResourceNotFoundError(name=name)

    async def generate_cluster_config(self, id: str) -> dict:
        name = self._cluster_name(id=id)
        if config := await self._get_config(name=name, model=models.DockFSConfig):
            return {
                "virtual_router_id": config.virtual_router_id,
                "vip": str(config.vip),
                "keepalived_password": SecretsClient.generate_random_password(),
            }
        raise exceptions.ResourceNotFoundError(name=name)

    async def set_node(self, id: str, node: models.DockFSNode, node_type: Literal["active", "passive"]) -> None:
        name = self._cluster_name(id=id)
        await self._hset(name=name, key=node_type, value=node.model_dump_json())

    async def set_cluster_status(self, id: str, status: data_types.DockFSStatus) -> None:
        name = self._cluster_name(id=id)
        await self._hset(name=name, key="status", value=str(status))

    async def delete_node(self, id: str, node: models.DockFSNode) -> None:
        await self._hdel(self.MAC_INDEX, node.mac)

    async def delete(self, id: str) -> None:
        name = self._cluster_name(id=id)
        await self.client.delete(name)
        await self._set_rem(self.INDEX, id)


class AutoscalingClient(RedisClient):
    INDEX: Final = "ol:autoscaling:pools"
    
    def _get_redis_name(self, pool_name: str) -> str:
        return f"{self.INDEX}:{pool_name}"

    async def generate_instance_hostname(self, pool_name: str) -> str:
        return await self._generate_unique_id(prefix=pool_name, count=6)

    async def pool_exists(self, pool_name: str) -> bool:
        return pool_name in await self._list_set_members(index=self.INDEX)

    async def set_pool(self, config: models.AutoscalingPoolConfiguration, *, create: bool = False) -> models.AutoscalingPool:
        if create and await self.pool_exists(pool_name=config.pool_name):
            raise exceptions.ResourceAlreadyExistsError(name=self._get_redis_name(pool_name=config.pool_name))
        name = self._get_redis_name(pool_name=config.pool_name)
        await self._mutate_object(name=name, submitted=config)
        await self._set_add(self.INDEX, config.pool_name)
        state = await self._get_state(name=name, model=models.AutoscalingPoolState)
        return models.AutoscalingPool(config=config, state=state)

    async def generate_member_create_params(self, pool_name: str, vmid: int) -> dict:
        name = self._get_redis_name(pool_name=pool_name)
        if config := await self._get_config(name=name, model=models.AutoscalingPoolConfiguration):
            sector = await SectorClient().get(id=config.sector)
            hostname = await self._generate_unique_id(prefix=config.pool_name, count=6)
            password = await SecretsClient().get_service_secret(service_name="autoscaling", service_id=config.pool_name, subservice_name="password")
            if isinstance(config.compute_config, models.LXCConfig):
                return {
                    "pool": config.pool_name,
                    "vmid": vmid,
                    "features": "nesting=1",
                    "ostemplate": config.compute_config.volume_id,
                    "hostname": hostname,
                    "cores": config.compute_config.cores,
                    "memory": config.compute_config.memory_gb * 1024,
                    "swap": config.compute_config.swap_mb,
                    "net0": f"name=eth0,bridge={config.sector},ip=dhcp,mtu=1450",
                    "rootfs": f"{config.compute_config.storage}:{config.compute_config.disk_size}",
                    "unprivileged": "1",
                    "password": password,
                    "searchdomain": "sector.internal",
                    "nameserver": f"{sector.config.dns_address.ip}",
                    "onboot": "1",
                }
            return {
                "pool": config.pool_name,
                "vmid": vmid,
                "name": hostname,
                "cores": config.compute_config.cores,
                "sockets": config.compute_config.sockets,
                "memory": config.compute_config.memory_gb * 1024,
                "cpu": "x86-64-v2-AES",
                "numa": 0,
                "agent": "enabled=1",
                "serial0": "socket",
                "scsi0": f"{config.compute_config.storage}:0,import-from={config.compute_config.volume_id}",
                "ide0": f"{config.compute_config.storage}:cloudinit",
                "citype": "nocloud",
                "ciuser": "root",
                "cipassword": password,
                "net0": f"virtio,bridge={config.sector},mtu=1450",
                "ipconfig0": "ip=dhcp",
                "searchdomain": "sector.internal",
                "nameserver": f"{sector.config.dns_address.ip}",
                "scsihw": "virtio-scsi-single",
                "ostype": "l26",
                "onboot": "1",
                "boot": "order=scsi0",
            }
        raise exceptions.ResourceNotFoundError(name=name)


class LogsClient(RedisClient):
    
    async def _format_logs(self, redis_result: list[tuple]) -> tuple[str, list[str]]:
        lines = []
        last_id = ""
        for event in redis_result:
            range_id, data = event
            if not last_id:
                last_id = range_id.decode()
            if b'trace' in data:
                lines.append(
                    f"{data[b'timestamp'].decode()} - {data[b'level'].decode()} - {data[b'trace'].decode()} - {data[b'message'].decode()}"
                )
            else:
                lines.append(
                    f"{data[b'timestamp'].decode()} - {data[b'level'].decode()} - {data[b'workflow'].decode()} - {data[b'message'].decode()}"
                )
        return last_id, lines
    
    async def get_workflow_logs(self, last_id: str = "") -> tuple[str, list[str]]:
        if last_id:
            redis_result = await self.client.xrevrange(name=EventStreams.WORKFLOW_LOGS, min=f"({last_id}", max="+")
        else:
            redis_result = await self.client.xrevrange(name=EventStreams.WORKFLOW_LOGS, count=50)
        return await self._format_logs(redis_result=redis_result)

    async def get_system_logs(self, last_id: str = "") -> tuple[str, list[str]]:
        if last_id:
            redis_result = await self.client.xrevrange(name=EventStreams.SYSTEM_LOGS, min=f"({last_id}", max="+")
        else:
            redis_result = await self.client.xrevrange(name=EventStreams.SYSTEM_LOGS, count=50)
        return await self._format_logs(redis_result=redis_result)


class ConduitClient(RedisClient):
    POOLS_INDEX: Final = "ol:conduit:pools"
    ENDPOINTS_INDEX: Final = "ol:conduit:endpoints"

    def _redis_name(self, index: str, id: str) -> str:
        return f"{index}:{id}"

    async def generate_pool_id(self) -> str:
        return await self._generate_unique_id(prefix="cpi", index=self.POOLS_INDEX)

    async def generate_endpoint_id(self) -> str:
        return await self._generate_unique_id(prefix="cpe", index=self.ENDPOINTS_INDEX)

    async def set_pool(self, config: models.ConduitPoolConfig) -> None:
        name = self._redis_name(index=self.POOLS_INDEX, id=config.id)
        await self._mutate_object(name=name, submitted=config)
        await self._set_add(self.POOLS_INDEX, config.id)

    async def get_pool(self, pool_id: str) -> models.ConduitPool:
        name = self._redis_name(index=self.POOLS_INDEX, id=pool_id)
        if config := await self._get_config(name=name, model=models.ConduitPoolConfig):
            state = await self._get_state(name=name, model=models.ConduitPoolState)
            return models.ConduitPool(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name)

    async def list_pools(self) -> list[models.ConduitPool]:
        return [
            await self.get_pool(pool_id=pool_id)
            for pool_id in await self._list_set_members(index=self.POOLS_INDEX)
        ]

    async def pool_exists(self, pool_id: str) -> bool:
        try:
            await self.get_pool(pool_id=pool_id)
        except exceptions.ResourceNotFoundError:
            return False
        else:
            return True

    async def pool_in_use(self, pool_id: str) -> bool:
        return any(pool_id == endpoint.config.pool for endpoint in await self.list_endpoints())

    async def delete_pool(self, pool_id: str) -> None:
        await self._set_rem(self.POOLS_INDEX, pool_id)
        name = self._redis_name(index=self.POOLS_INDEX, id=pool_id)
        await self.client.delete(name)

    async def set_endpoint(self, config: models.ConduitEndpointConfig) -> None:
        name = self._redis_name(index=self.ENDPOINTS_INDEX, id=config.id)
        await self._mutate_object(name=name, submitted=config)
        await self._set_add(self.ENDPOINTS_INDEX, config.id)

    async def get_endpoint(self, endpoint_id: str) -> models.ConduitEndpoint:
        name = self._redis_name(index=self.ENDPOINTS_INDEX, id=endpoint_id)
        if config := await self._get_config(name=name, model=models.ConduitEndpointConfig):
            state = await self._get_state(name=name, model=models.ConduitEndpointState)
            return models.ConduitEndpoint(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name)

    async def endpoint_exists(self, endpoint_id: str) -> bool:
        try:
            await self.get_endpoint(endpoint_id=endpoint_id)
        except exceptions.ResourceNotFoundError:
            return False
        else:
            return True

    async def list_endpoints(self) -> list[models.ConduitEndpoint]:
        return [
            await self.get_endpoint(endpoint_id=endpoint_id)
            for endpoint_id in await self._list_set_members(index=self.ENDPOINTS_INDEX)
        ]

    async def delete_endpoint(self, endpoint_id: str) -> None:
        await self.remove_endpoint_association(endpoint_id=endpoint_id)
        await self._set_rem(self.ENDPOINTS_INDEX, endpoint_id)
        name = self._redis_name(index=self.ENDPOINTS_INDEX, id=endpoint_id)
        await self.client.delete(name)

    async def generate_params(self, endpoint_id: str, vmid: int) -> dict:
        endpoint = await self.get_endpoint(endpoint_id=endpoint_id)
        infra = await ClusterClient().get_infra_appliances()
        storage = (await ClusterClient().get_defaults()).vztmpl
        sector = await SectorClient().get(id=endpoint.config.sector)
        return {
            "features": "nesting=1",
            "ostemplate": infra.appliances["conduit"].volume_id,
            "hostname": endpoint.config.id,
            "cores": 2,
            "memory": 512,
            "swap": 256,
            "net0": f"name=eth0,bridge={sector.config.id},ip=dhcp",
            "net1": f"name=eth1,bridge=vmbr0,ip=dhcp",
            "rootfs": f"{storage}:4",
            "unprivileged": "1",
            "vmid": vmid,
            "password": SecretsClient.generate_random_password(),
            "searchdomain": "sector.internal",
            "nameserver": str(sector.config.dns_address.ip),
            "onboot": "1",
        }

    async def set_target_health(self, pool_id: str, target_id: str, status: str) -> None:
        name = self._redis_name(index=self.POOLS_INDEX, id=pool_id)
        state = await self._get_state(name=name, model=models.ConduitPoolState)
        state.targets_health[target_id] = status
        await self._hset(name=name, key="targets_health", value=json.dumps(state.targets_health))

    async def add_endpoint_association(self, endpoint_id: str) -> None:
        endpoint = await self.get_endpoint(endpoint_id=endpoint_id)
        name = self._redis_name(index=self.POOLS_INDEX, id=endpoint.config.pool)
        pool_state = await self._get_state(name=name, model=models.ConduitPoolState)
        pool_state.associated_endpoints.append(endpoint_id)
        await self._hset(name=name, key="associated_endpoints", value=json.dumps(pool_state.associated_endpoints))

    async def remove_endpoint_association(self, endpoint_id: str) -> None:
        endpoint = await self.get_endpoint(endpoint_id=endpoint_id)
        name = self._redis_name(index=self.POOLS_INDEX, id=endpoint.config.pool)
        pool_state = await self._get_state(name=name, model=models.ConduitPoolState)
        if endpoint_id in pool_state.associated_endpoints:
            pool_state.associated_endpoints.remove(endpoint_id)
            await self._hset(name=name, key="associated_endpoints", value=json.dumps(pool_state.associated_endpoints))

    async def set_listener_address(self, endpoint_id: str, address: IPv4Interface) -> None:
        name = self._redis_name(index=self.ENDPOINTS_INDEX, id=endpoint_id)
        await self._hset(name=name, key="listener_address", value=str(address.ip))

    async def report_health(self, endpoint_id: str, health_results: dict[str, str]) -> None:
        name = self._redis_name(index=self.ENDPOINTS_INDEX, id=endpoint_id)
        await self._hset(name=name, key="health_results", value=json.dumps(health_results))
