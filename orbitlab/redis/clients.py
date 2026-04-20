import asyncio
import base64
from datetime import UTC, datetime, timedelta
from functools import cached_property
import hashlib
from ipaddress import IPv4Address, IPv4Interface, ip_address
import json
import os
import secrets
import string
import time
from typing import Final, Literal, TypeVar, overload

from cryptography import x509
from pydantic import BaseModel
from redis import WatchError
from redis.asyncio import Redis
from redis.client import Pipeline
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.keywrap import aes_key_wrap, aes_key_unwrap
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from orbitlab import constants, data_types
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
    
    async def _mutate_object(self, name: str, submitted: models.ResourceConfig) -> models.ResourceConfig:
        for attempt in range(1, self._cas_max_retries + 1):
            async with self.client.pipeline(transaction=True) as pipeline:
                try:
                    print("Attempt: ", attempt)
                    await pipeline.watch(name)
                    if raw := await self._get_decoded(name=name, key="config", pipeline=pipeline):
                        current = type(submitted).model_validate_json(raw)
                    else:
                        current = submitted
                    
                    if current == submitted:
                        # If the resource configuration hasn't change, don't mutate.
                        await pipeline.unwatch()
                        return current
                    
                    if current.version != submitted.version:
                        raise RuntimeError(
                            f"CAS conflict for '{name}': "
                            f"submitted version={submitted.version}, "
                            f"Redis version={current.version}"
                        )
                    new_version = submitted.model_copy(
                        update={"version": submitted.version + 1, "last_update": int(time.time())}
                    )
                    pipeline.multi()
                    pipeline.hset(name=name, key="config", value=new_version.model_dump_json()) 
                except WatchError:
                    await asyncio.sleep(1)
                    continue
        raise RuntimeError(
            f"CAS update failed after {self._cas_max_retries} retries due to contention: {name}"
        )

    async def _list_keys(self, name: str, *, ignore_config: bool = False, pipeline: Pipeline | None = None) -> list[str]:
        if pipeline:
            value: list[bytes] = await pipeline.hkeys(name=name)
        else:
            value: list[bytes] = await self.client.hkeys(name=name)
        if ignore_config:
            return [key.decode() for key in value if key != "config"]
        return [key.decode() for key in value]

    async def _get_decoded(self, name: str, key: str, *, pipeline: Pipeline | None = None) -> str | None:
        if pipeline:
            value: bytes | None = await pipeline.hget(name=name, key=key)
        else:
            value: bytes | None = await self.client.hget(name=name, key=key)
        if not value:
            return None
        return value.decode()

    async def _get_state(self, name: str, model: type[T]) -> T:
        state = {
            key: await self._get_decoded(name=name, key=key) for key in await self._list_keys(name=name, ignore_config=True)
        }
        return model.model_validate(state)

    async def _get_config(self, name: str, model: type[T]) -> T | None:
        value: bytes | None = await self.client.hget(name=name, key="config")
        if not value:
            return None
        
        resource = json.loads(value.decode())
        resource["state"] = {
            key: await self._get_decoded(name=name, key=key) for key in await self._list_keys(name=name, ignore_config=True)
        }
        return model.model_validate(resource)

    async def _hset(self, name: str, key: str, value: bytes | str | int) -> None:
        if isinstance(value, bytes):
            value = value.decode()
        elif isinstance(value, int):
            value = str(value)
        await self.client.hset(name=name, key=key, value=value)

    async def _list_set_members(self, index: str) -> list[str]:
        members: set[bytes] = await self.client.smembers(name=index)
        return [member.decode() for member in members]

    async def _generate_unique_id(self, prefix: str, *, count: int = 12, index: str = "", existing: list[str] | None = None) -> str:
        if not index and not existing:
            random_id = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(count))
            return f"{prefix}-{random_id}"
        if index and not existing:
            existing = await self._list_set_members(index=index)
        while True:
            random_id = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(count))
            resource_id = f"{prefix}-{random_id}"
            if resource_id not in existing:
                break
        return resource_id


class ClusterClient(RedisClient):
    NAME: Final = "ol:cluster"
    INDEX: Final = "ol:cluster:nodes"

    def _get_node_redis_name(self, node: str) -> str:
        return f"{self.INDEX}:{node}"

    async def is_initialized(self) -> bool:
        return bool(await self._get_decoded(name=self.NAME, key="initialized"))

    async def set_initialized(self) -> None:
        await self._hset(name=self.NAME, key="initialized", value="True")

    async def get_defaults(self) -> models.Defaults:
        if defaults := await self._get_decoded(name=self.NAME, key="defaults"):
            return models.Defaults.model_validate_json(defaults)
        raise exceptions.ResourceNotFoundError(name=self.NAME, key="defaults")

    async def set_defaults(self, defaults: models.Defaults) -> None:
        await self._hset(name=self.NAME, key="defaults", value=defaults.model_dump_json())

    async def get_infra_appliances(self) -> models.InfraAppliances:
        if appliances := await self._get_decoded(name=self.NAME, key="appliances"):
            return models.InfraAppliances.model_validate_json(appliances)
        raise exceptions.ResourceNotFoundError(name=self.NAME, key="appliances")
    
    async def set_infra_appliances(self, appliances: models.InfraAppliances) -> models.InfraAppliances:
        await self._hset(name=self.NAME, key="appliances", value=appliances.model_dump_json())

    # async def set_node(self, node: models.NodeConfig) -> models.Node:
    #     name = self._get_node_redis_name(node=node.name)
    #     config: models.NodeConfig = await self._mutate_object(name=name, submitted=node)
    #     await self.client.sadd(self.INDEX, node.name)
    #     online = await ProxmoxCluster().node_online(name=config.name)
    #     maintenance_mode = await ProxmoxCluster().node_maintenance_mode(name=config.name)
    #     await self._hset(name=name, key="online", value=online)
    #     await self._hset(name=name, key="maintenance_mode", value=maintenance_mode)
    #     return models.Node(config=config, state=models.NodeState(online=online, maintenance_mode=maintenance_mode))
    
    async def get_node(self, node: str) -> models.Node:
        name = self._get_node_redis_name(node=node)
        if config := await self._get_config(name=name, model=models.NodeConfig):
            state = await self._get_state(name=name, model=models.NodeState)
            return models.Node(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name, key="config")
    
    async def list_nodes(self) -> list[models.Node]:
        return [await self.get_node(node=node) for node in await self._list_set_members(index=self.INDEX)]


class BackplaneClient(RedisClient):
    NAME: Final = "ol:backplane"
    ASSIGNMENTS_INDEX: Final = "ol:backplane:assignments"
    TAGS_INDEX: Final = "ol:backplane:vlan-tags"
    VRID_INDEX: Final = "ol:backplane:vrid"

    async def get(self) -> models.Backplane:
        if config := await self._get_config(name=self.NAME, model=models.Backplane):
            return config
        raise exceptions.ResourceNotFoundError(name=self.NAME)

    async def set(self, config: models.Backplane) -> models.Backplane:
        return await self._mutate_object(name=self.NAME, submitted=config)

    async def get_next_vlan_tag(self, start: int = 1000, end: int = 9999) -> int | None:
        existing_tags = [int(tag) for tag in await self._list_set_members(index=self.TAGS_INDEX)]
        if tag := next((i for i in range(start, end + 1) if i not in existing_tags), None):
            await self.client.sadd(self.TAGS_INDEX, tag)
            return tag
        return None

    async def release_vlan_tag(self, tag: int) -> None:
        await self.client.srem(self.TAGS_INDEX, tag)

    async def get_dns_vmid(self) -> int:
        if dns_vmid := await self._get_decoded(name=self.NAME, key="dns-vmid"):
            return int(dns_vmid)
        raise exceptions.ResourceNotFoundError(name="DNS VMID")

    @overload
    async def get_next_available_ip(self, *, count: None = None) -> IPv4Interface: ...

    @overload
    async def get_next_available_ip(self, *, count: int) -> list[IPv4Interface]: ...

    async def get_next_available_ip(self, *, count: int | None = None) -> IPv4Interface | list[IPv4Interface]:
        """Get the next available IP address in the subnet."""
        backplane = await self.get()
        assigned = [IPv4Interface(address) for address in await self._list_set_members(index=self.ASSIGNMENTS_INDEX)]
        hosts = list(backplane.cidr_block.hosts())
        usable = hosts[constants.NetworkSettings.RESERVED_INFRA_IPS:constants.NetworkSettings.RESERVED_BROADCAST_IPS]
        if count:
            available_generator = iter(
                IPv4Interface(f"{ip}/{backplane.cidr_block.prefixlen}") for ip in usable if ip not in assigned
            )
            assigned = [next(available_generator) for _ in range(count)]
            await self.client.sadd(self.ASSIGNMENTS_INDEX, *[str(ip) for ip in assigned])
            return assigned
        assigned = next(iter(
            IPv4Interface(f"{ip}/{backplane.cidr_block.prefixlen}") for ip in usable if ip not in assigned
        ))
        await self.client.sadd(self.ASSIGNMENTS_INDEX, str(assigned))
        return assigned

    async def get_next_available_vrid(self) -> int:
        assigned = [int(vrid) for vrid in await self._list_set_members(index=self.VRID_INDEX)]
        vrid = next(iter([vrid for vrid in range(1, 256) if vrid not in assigned]))
        await self.client.sadd(self.VRID_INDEX, vrid)
        return vrid

    async def release_assigned_ips(self, *addresses: IPv4Interface) -> None:
        await self.client.srem(self.ASSIGNMENTS_INDEX, *[str(address) for address in addresses])

    async def generate_backplane_dns_params(self, vmid: int) -> dict:
        backplane = await self.get()
        infra = await ClusterClient().get_infra_appliances()
        storage = (await ClusterClient().get_defaults()).vztmpl
        await self._hset(name=self.NAME, key="dns-vmid", value=vmid)
        return {
            "features": "nesting=1",
            "ostemplate": infra.appliances["backplane-dns"].volume_id,
            "hostname": "backplane-dns",
            "cores": 1,
            "memory": 512,
            "swap": 512,
            "net0": (
                f"name=eth0,"
                f"bridge={backplane.vnet_id},"
                f"ip={backplane.dns_address},"
                f"gw={backplane.default_gateway_address.ip}"
            ),
            "net1": (
                f"name=eth1,"
                f"bridge={backplane.vnet_id},"
                f"ip={backplane.orbital_relay_address.ip},"
                f"gw={backplane.default_gateway_address.ip}"
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
        if member := await self.client.srandmember(name=self.MEMBER_INDEX):
            return models.ETCDMember.model_validate_json(member)
        raise exceptions.ResourceNotFoundError(name=self.MEMBER_INDEX)
    
    async def generate_create_params(self, vmid: int) -> dict:
        cluster = ClusterClient()
        dns = DNSClient()
        
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
        await asyncio.gather(
            self.client.sadd(self.MEMBER_INDEX, member.model_dump_json()),
            dns.add_backplane_a_records("etcd", models.ARecord(address=member.address.ip)),
            dns.add_backplane_a_records(member.name, models.ARecord(address=member.address.ip)),
            dns.add_backplane_srv_records("etcd-server", "tcp", models.SRVRecord(host=member.name, port=2380)),
            dns.add_backplane_srv_records("etcd-client", "tcp", models.SRVRecord(host=member.name, port=2379))
        )
        return {
            "pool": "orbitlab-etcd",
            "features": "nesting=1",
            "ostemplate": infra.appliances["etcd"].volume_id,
            "hostname": member.name,
            "cores": 2,
            "memory": 1024,
            "swap": 1024,
            "net0": (
                f"name=eth0,bridge={backplane.vnet_id},ip={member.address},gw={backplane.default_gateway_address.ip}"
            ),
            "rootfs": f"{defaults.vztmpl}:8",
            "unprivileged": "1",
            "vmid": vmid,
            "password": SecretsClient.generate_random_password(),
            "searchdomain": "orbitlab.internal",
            "nameserver": f"{backplane.dns_address.ip}",
            "onboot": "1",
        }

    async def remove_member(self, member: models.ETCDMember) -> None:
        dns = DNSClient()
        await asyncio.gather(
            BackplaneClient().release_assigned_ips(member.address),
            dns.remove_backplane_a_records("etcd", models.ARecord(address=member.address.ip)),
            dns.remove_backplane_a_records(member.name, models.ARecord(address=member.address.ip)),
            dns.remove_backplane_srv_records("etcd-server", "tcp", models.SRVRecord(host=member.name, port=2380)),
            dns.remove_backplane_srv_records("etcd-client", "tcp", models.SRVRecord(host=member.name, port=2379)),
            self.client.srem(self.MEMBER_INDEX, member.model_dump_json())
        )

    async def get_version(self) -> str:
        if version := await self._get_decoded(name=self.NAME, key="version"):
            return version
        return ""

    async def set_version(self, version: str) -> None:
        await self._hset(name=self.NAME, key="version", value=version)

    # async def is_enabled(self) -> bool:
    #     return bool(await self._get_decoded(name=self.NAME, key="enabled"))

    # async def enable(self) -> None:
    #     await self._hset(name=self.NAME, key="enabled", value="true")
    
    # async def disable(self) -> None:
    #     await self._hset(name=self.NAME, key="enabled", value="")

    async def get_status(self) -> data_types.ETCDStatus:
        if status := await self._get_decoded(name=self.NAME, key="status"):
            return data_types.ETCDStatus(status)
        return data_types.ETCDStatus.ABSENT

    async def set_status(self, status: data_types.ETCDStatus) -> None:
        await self._hset(name=self.NAME, key="status", value=status)


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
                value=models.ARecord(address=backplane.dns_address.ip).model_dump_json(),
            )
    
    async def create_sector_zone(self, sector_id: str) -> None:
        if not await self.zone_exists(zone=self.SECTOR_ZONE, sector_id=sector_id):
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
                value=models.ARecord(address=sector.config.dns_address.ip).model_dump_json(),
            )

    async def add_backplane_a_records(self, hostname: str, *records: models.ARecord, zone_type: data_types.ZoneType = "internal") -> None:
        name = self._zone_name(zone_type=zone_type)
        if existing := await self._get_decoded(name=name, key=hostname):
            a_records = models.ARecords.model_validate_json(existing)
        else:
            a_records = models.ARecords()
        a_records.a.extend(list(records))
        await self._hset(name=name, key=hostname, value=a_records.model_dump_json())

    async def remove_backplane_a_records(self, hostname: str, *records: models.ARecord, zone_type: data_types.ZoneType = "internal") -> None:
        name = self._zone_name(zone_type=zone_type)
        if existing := await self._get_decoded(name=name, key=hostname):
            a_records = models.ARecords.model_validate_json(existing)
            for record in records:
                a_records.a.remove(record)
            if a_records.valid:
                return await self._hset(name=name, key=hostname, value=a_records.model_dump_json())
            await self.client.hdel(name, hostname)
            return
        raise exceptions.ResourceNotFoundError(name=name, key=hostname)

    async def add_backplane_srv_records(self, service: str, protocol: Literal["tcp", "udp"], *records: models.SRVRecord) -> None:
        name = self._zone_name(zone_type="internal")
        hostname = f"_{service}._{protocol}"
        if existing := await self._get_decoded(name=name, key=hostname):
            srv_records = models.SRVRecords.model_validate_json(existing)
        else:
            srv_records = models.SRVRecords()
        srv_records.srv.extend(list(records))
        await self._hset(name=name, key=hostname, value=srv_records.model_dump_json())

    async def remove_backplane_srv_records(self, service: str, protocol: Literal["tcp", "udp"], *records: models.SRVRecord) -> None:
        name = self._zone_name(zone_type="internal")
        hostname = f"_{service}._{protocol}"
        if existing := await self._get_decoded(name=name, key=hostname):
            srv_records = models.SRVRecords.model_validate_json(existing)
            for record in records:
                srv_records.srv.remove(record)
            if srv_records.valid:
                return await self._hset(name=name, key=hostname, value=srv_records.model_dump_json())
            await self.client.hdel(name, hostname)
            return
        raise exceptions.ResourceNotFoundError(name=name, key=hostname)    

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
        
        if not await self.zone_exists(zone=self.SECTOR_ZONE, sector_id=sector_id):
            raise exceptions.ResourceNotFoundError(name=name)

        if existing := await self._get_decoded(name=name, key=hostname):
            a_records = models.ARecords.model_validate_json(existing)
        else:
            a_records = models.ARecords()
        a_records.a.extend(list(records))
        await self._hset(name=name, key=hostname, value=a_records.model_dump_json())

    async def remove_sector_a_records(self, sector_id: str, hostname: str, *records: models.ARecord) -> None:
        name = self._zone_name(zone_type="internal", sector_id=sector_id)
        if existing := await self._get_decoded(name=name, key=hostname):
            a_records = models.ARecords.model_validate_json(existing)
            for record in records:
                a_records.a.remove(record)
            if a_records.valid:
                return await self._hset(name=name, key=hostname, value=a_records.model_dump_json())
            await self.client.hdel(name, hostname)
            return
        raise exceptions.ResourceNotFoundError(name=name, key=hostname)


class SectorClient(RedisClient):
    INDEX: Final = "ol:sectors"
    
    def _get_name(self, id: str) -> str:
        return f"ol:sector:{id}"
    
    async def list_sectors(self) -> list[models.Sector]:
        return [await self.get(id=id, required=True) for id in await self._list_set_members(index=self.INDEX)]
    
    async def sector_exists(self, id: str) -> bool:
        return id in await self._list_set_members(index=self.INDEX)
    
    async def get(self, id: str) -> models.Sector:
        name = self._get_name(id=id)
        if config := await self._get_config(name=name, model=models.SectorConfiguration):
            state = await self._get_state(name=name, model=models.SectorState)
            return models.Sector(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name)

    async def set(self, config: models.SectorConfiguration) -> models.Sector:
        config = await self._mutate_object(name=self._get_name(id=config.id), submitted=config)
        await self.client.sadd(self.INDEX, config.id)
        return await self.get(id=config.id, required=True)

    async def generate_gateway_params(self, id: str, vmid: int) -> dict:
        name = self._get_name(id=id)
        if config := await self._get_config(name=name, model=models.SectorConfiguration):
            infra = await ClusterClient().get_infra_appliances()
            backplane = await BackplaneClient().get()
            address = await BackplaneClient().get_next_available_ip()
            await self._hset(name=name, key="gateway_vmid", value=vmid)
            return {
                "features": "nesting=1",
                "ostemplate": infra.appliances["gateway"].volume_id,
                "hostname": f"{config.bridge}-gw",
                "cores": "1",
                "memory": "512",
                "swap": "512",
                "net0": f"name=eth0,bridge={config.bridge},ip={config.default_gateway}",
                "net1": (
                    "name=eth1,"
                    f"bridge={backplane.vnet_id},"
                    f"ip={address},"
                    f"gw={backplane.default_gateway_address.ip}"
                ),
                "net2": f"name=eth2,bridge={config.bridge},ip={config.dns_address}",
                "rootfs": f"{config.storage}:8",
                "unprivileged": "1",
                "vmid": vmid,
                "password": SecretsClient.generate_random_password(),
                "searchdomain": "sector.internal",
                "nameserver": str(backplane.dns_address.ip),
                "onboot": "1",
            }
    
    async def set_gateway_version(self, id: str, version: str) -> None:
        await self._hset(name=self._get_name(id=id), key="gateway_version", value=version)
    
    async def get_gateway_version(self, id: str) -> str:
        if version := await self._get_decoded(name=self._get_name(id=id), key="gateway_version"):
            return version
        return ""
    
    async def set_sector_status(self, id: str, status: data_types.SectorStatus) -> None:
        await self._hset(name=self._get_name(id=id), key="status", value=status)
    
    async def get_sector_status(self, id: str) -> data_types.SectorStatus:
        if status := await self._get_decoded(name=self._get_name(id=id), key="status"):
            return data_types.SectorStatus(status)
        return data_types.SectorStatus.PENDING
    
    async def acquire_vip(self, id: str) -> models.SectorVIP:
        sector = await self.get(id=id)
        vip = sector.get_available_vip()
        sector.state.vips[vip.virtual_router_id] = vip.address
        serialized = sector.state.model_dump()
        await self._hset(name=self._get_name(id=id), key="vips", value=serialized["vips"])

    async def release_vips(self, *virtual_router_ids: int, id: str) -> None:
        sector = await self.get(id=id)
        for vrid in virtual_router_ids:
            del sector.state.vips[vrid]
        serialized = sector.state.model_dump()
        await self._hset(name=self._get_name(id=id), key="vips", value=serialized["vips"])

    async def delete(self, id: str) -> None:
        await self.client.delete(self._get_name(id=id))


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
        await self.client.sadd(self.INDEX, secret_name)
        return secret
    
    async def secret_exists(self, secret_name: str) -> bool:
        return bool(await self.get_current_version(secret_name=secret_name))
    
    async def get(self, secret_name: str, version: int | None = None) -> models.Secret:
        if not version:
            version = await self.get_current_version(secret_name=secret_name)
        name = self._get_name(secret_name=secret_name)
        key = f"v{version}"
        if blob := await self._get_decoded(name=name, key=key):
            return self._decrypt(blob=blob)
        raise exceptions.ResourceNotFoundError(name=name, key=key)

    async def list_secrets(self) -> list[models.Secret]:
        return [
            await self.get(secret_name=secret_name)
            for secret_name in await self._list_set_members(index=self.INDEX)
        ]

    async def rotate(self, secret_name: str, version: int, new_value: str) -> models.Secret:
        secret = await self.get(secret_name=secret_name, version=version)
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
        await self.client.hdel(name, f"v{secret.secret_version}")
        return await self.get(secret_name=secret_name, version=previous_version)

    async def delete(self, secret_name: str) -> None:
        await self.client.delete(self._get_name(secret_name=secret_name))

    async def create_lxc_password(self, lxc_id: str, password: str = "") -> models.Secret:
        return await self.create(
            secret_name=f"/orbitlab/lxc/{lxc_id}",
            value=password or self.generate_random_password(),
            description=f"Password for LXC {lxc_id}",
        )

    async def get_lxc_password(self, lxc_id: str) -> str:
        secret = await self.get(secret_name=f"/orbitlab/lxc/{lxc_id}")
        return secret.secret_string.get_secret_value()

    async def delete_lxc_password(self, lxc_id: str) -> None:
        await self.delete(secret_name=f"/orbitlab/lxc/{lxc_id}")

    async def create_vm_password(self, vm_id: str, password: str | None = None) -> models.Secret:
        return await self.create(
            secret_name=f"/orbitlab/vm/{vm_id}",
            value=password or self.generate_random_password(),
            description=f"Password for VM {vm_id}",
        )

    async def get_vm_password(self, vm_id: str) -> str:
        secret = await self.get(secret_name=f"/orbitlab/vm/{vm_id}")
        return secret.secret_string.get_secret_value()

    async def delete_vm_password(self, vm_id: str) -> None:
        await self.delete(secret_name=f"/orbitlab/vm/{vm_id}")

    async def create_service_secret(self, service_name: str, service_id: str, *, value: str = "", subservice_name: str = "") -> models.Secret:
        secret_name = self._get_service_secret_name(service_name=service_name, service_id=service_id, subservice_name=subservice_name)
        return await self.create(
            secret_name=secret_name,
            value=value or self.generate_random_password(),
            description=f"{service_name} secret for {service_id}",
        )

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
        await self.client.sadd(self.PKI_KEY_INDEX, secret_name)

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
        await self.client.srem(self.PKI_KEY_INDEX, secret_name)

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

    def _get_name(self, index: str, common_name: str) -> str:
        return f"{index}:{common_name}"

    async def create_certificate_authority(self, subject: models.Subject, key_usage: list[data_types.KeyUsageTypes]) -> models.RootCert:
        # Create self-signed certificate and output PEMs
        private_key = rsa.generate_private_key(
            public_exponent=constants.PKI.RSA_PUBLIC_EXPONENT,
            key_size=constants.PKI.RSA_KEY_SIZE,
        )
        subject_name = issuer_name = subject.to_x509()
        now = datetime.now(UTC)
        serial_number = secrets.randbits(128)
        not_before = now - timedelta(minutes=5)
        not_after = now + timedelta(days=constants.PKI.ROOT_CA_DAYS_VALID)
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
        await self.client.sadd(self.ROOT_CERTS_INDEX, subject.common_name)
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
        await self.client.delete(name=name)
        await self.client.srem(self.ROOT_CERTS_INDEX, common_name)

    async def create_intermediate_certificate(self, common_name: str, root_ca_common_name: str, domain_constraint: str) -> models.IntermediateCert:
        """Create a new intermediate certificate signed by the specified root CA."""
        root = await self.get_root_certificate(common_name=root_ca_common_name)
        root_key = serialization.load_pem_private_key(
            (await SecretsClient().get_private_key(cert_common_name=root_ca_common_name)).encode(),
            password=None,
        )
        root_cert = x509.load_pem_x509_certificate(root.certificate.encode())

        private_key = rsa.generate_private_key(
            public_exponent=constants.PKI.RSA_PUBLIC_EXPONENT,
            key_size=constants.PKI.RSA_KEY_SIZE,
        )
        now = datetime.now(UTC)
        serial_number = secrets.randbits(128)
        not_before = now - timedelta(minutes=5)
        not_after = now + timedelta(days=constants.PKI.INTERMEDIATE_CA_DAYS_VALID)
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
        await self.client.sadd(self.INTERMEDIATE_CERTS_INDEX, intermediate_subject.common_name)
        return certificate

    async def get_intermediate_certificate(self, common_name: str) -> models.IntermediateCert:
        name = self._get_name(index=self.INTERMEDIATE_CERTS_INDEX, common_name=common_name)
        if data := await self.client.get(name=name):
            return models.IntermediateCert.model_validate_json(data)
        raise exceptions.ResourceNotFoundError(name=name)

    async def list_intermediate_certificates(self) -> list[models.IntermediateCert]:
        return [
            await self.get_root_certificate(common_name=common_name)
            for common_name in await self._list_set_members(index=self.INTERMEDIATE_CERTS_INDEX)
        ]

    async def delete_intermediate_certificate(self, common_name: str) -> None:
        name = self._get_name(index=self.INTERMEDIATE_CERTS_INDEX, common_name=common_name)
        await self.client.delete(name=name)
        await self.client.srem(self.INTERMEDIATE_CERTS_INDEX, common_name)

    async def create_leaf_certificate(self, common_name: str, san_dns: list[str], san_ips: list[str], signing_ca_common_name: str, *, server_auth: bool) -> models.LeafCert:
        signer = await self.get_intermediate_certificate(common_name=signing_ca_common_name)
        
        
        private_key = rsa.generate_private_key(
            public_exponent=constants.PKI.RSA_PUBLIC_EXPONENT,
            key_size=constants.PKI.RSA_KEY_SIZE,
        )
        key_usage = [data_types.KeyUsageTypes.DIGITAL_SIGNATURE, data_types.KeyUsageTypes.KEY_AGREEMENT]
        if server_auth:
            key_usage.append(data_types.KeyUsageTypes.KEY_ENCIPHERMENT)

        leaf_subject = signer.subject.model_copy()
        leaf_subject.common_name = common_name

        builder = x509.CertificateSigningRequestBuilder().subject_name(leaf_subject.to_x509())
        if san_dns or san_ips:
            general_names = [x509.DNSName(value=name) for name in san_dns]
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
            chain=x509.load_pem_x509_certificate(signer.certificate.encode()).public_bytes(serialization.Encoding.PEM).decode()
        )

        name = self._get_name(index=self.LEAF_CERTS_INDEX, common_name=leaf_subject.common_name)
        await self.client.set(name=name, value=certificate.model_dump_json())
        await SecretsClient().store_private_key(cert_common_name=leaf_subject.common_name, key_pem=key_pem)
        await self.client.sadd(self.LEAF_CERTS_INDEX, leaf_subject.common_name)
        return certificate

    async def sign_csr(self, csr_der: str, signing_ca_common_name: str) -> str:
        signer = await self.get_intermediate_certificate(common_name=signing_ca_common_name)
        csr = x509.load_pem_x509_csr(csr_der.encode())
        signing_key = serialization.load_pem_private_key(
            (await SecretsClient().get_private_key(cert_common_name=signing_ca_common_name)).encode(),
            password=None,
        )
        signing_cert = x509.load_pem_x509_certificate(signer.certificate.encode())

        now = datetime.now(UTC)
        serial_number = secrets.randbits(128)
        not_before = now - timedelta(minutes=5)
        not_after = now + timedelta(days=constants.PKI.LEAF_CA_DAYS_VALID)

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
        await self.client.delete(name=name)
        await self.client.srem(self.LEAF_CERTS_INDEX, common_name)


class SSHKeyClient(RedisClient):
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
                public_exponent=constants.PKI.RSA_PUBLIC_EXPONENT,
                key_size=constants.PKI.RSA_KEY_SIZE,
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
        await self.client.sadd(self.INDEX, key_pair_name)
        return ssh_key

    async def get_key_pair(self, key_pair_name: str) -> models.SSHKey:
        if not await self.key_pair_exists(key_pair_name=key_pair_name):
            raise exceptions.ResourceNotFoundError(name=self._get_name(key_pair_name=key_pair_name))
        data = await self.client.get(name=self._get_name(key_pair_name=key_pair_name))
        return models.SSHKey.model_validate_json(data)

    async def get_private_key(self, key_pair_name: str) -> models.SSHKey:
        if not await self.key_pair_exists(key_pair_name=key_pair_name):
            raise exceptions.ResourceNotFoundError(name=self._get_name(key_pair_name=key_pair_name))
        return await SecretsClient().get_private_key(cert_common_name=key_pair_name, ssh=True)

    async def delete_key_pair(self, key_pair_name: str) -> None:
        await self.client.delete(name = self._get_name(key_pair_name=key_pair_name))
        await self.client.srem(self.INDEX, key_pair_name)
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
    async def set_appliance(self, appliance_type: Literal["base"], config: models.BaseApplianceConfig) -> models.BaseAppliance: ...

    @overload
    async def set_appliance(self, appliance_type: Literal["custom"], config: models.CustomApplianceConfig) -> models.CustomAppliance: ...

    async def set_appliance(self, appliance_type: Literal["base", "custom"], config: models.BaseApplianceConfig | models.CustomApplianceConfig) -> models.BaseAppliance | models.CustomAppliance:
        index = self.BASE_APPLIANCE_INDEX if appliance_type == "base" else self.CUSTOM_APPLIANCE_INDEX
        name = self._appliance_name(id=config.id, index=self.BASE_APPLIANCE_INDEX)
        config = await self._mutate_object(name=name, submitted=config)
        await self.client.sadd(index, config.id)
        if appliance_type == "base":
            state = await self._get_state(name=name, model=models.BaseApplianceState)
            return models.BaseAppliance(config=config, state=state)
        state = await self._get_state(name=name, model=models.CustomApplianceState)
        return models.CustomAppliance(config=config, state=state)
    
    @overload
    async def get_appliance(self, appliance_type: Literal["base"], id: str) -> models.BaseAppliance: ...

    @overload
    async def get_appliance(self, appliance_type: Literal["custom"], id: str) -> models.CustomAppliance: ...
    
    async def get_appliance(self, appliance_type: Literal["base", "custom"], id: str) -> models.BaseAppliance | models.CustomAppliance:
        if appliance_type == "base":
            index = self.BASE_APPLIANCE_INDEX
            config_model = models.BaseApplianceConfig
            state_model = models.BaseApplianceState
            return_model = models.BaseAppliance
        else:
            index: Literal['ol:appliances:base'] = self.CUSTOM_APPLIANCE_INDEX
            config_model = models.CustomApplianceConfig
            state_model = models.CustomApplianceState
            return_model = models.CustomAppliance
            
        name = self._appliance_name(id=id, index=index)
        if config := await self._get_config(name=name, model=config_model):
            state = await self._get_state(name=name, model=state_model)
            return return_model(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name)

    @overload
    async def list_appliances(self, appliance_type: Literal["base"]) -> list[models.BaseAppliance]: ...

    @overload
    async def list_appliances(self, appliance_type: Literal["custom"]) -> list[models.CustomAppliance]: ...

    async def list_appliances(self, appliance_type: Literal["base", "custom"]) -> list[models.BaseAppliance | models.CustomAppliance]:
        index = self.BASE_APPLIANCE_INDEX if appliance_type == "base" else self.CUSTOM_APPLIANCE_INDEX
        return [await self.get_appliance(appliance_type=appliance_type, id=id) for id in await self._list_set_members(index=index)]

    async def delete_appliance(self, appliance_type: Literal["base", "custom"], id: str) -> None:
        index = self.BASE_APPLIANCE_INDEX if appliance_type == "base" else self.CUSTOM_APPLIANCE_INDEX
        await asyncio.gather(
            self.client.delete(self._appliance_name(id=id, index=index)),
            self.client.srem(index, id)
        )

    async def set_appliance_downloaded(self, id: str, volume_id: str) -> None:
        name = self._appliance_name(id=id, index=self.BASE_APPLIANCE_INDEX)
        if await self.appliance_exists(appliance_type="base", id=id):
            await asyncio.gather(
                self._hset(name=name, key="volume_id", value=volume_id),
                self._hset(name=name, key="download_date", value=datetime.now(UTC).isoformat())
            )
        raise exceptions.ResourceNotFoundError(name=name)
    
    async def set_workflow_status(self, id: str, workflow_status: data_types.TemplateWorkflowStatus) -> None:
        name = self._appliance_name(id=id, index=self.CUSTOM_APPLIANCE_INDEX)
        if await self.appliance_exists(appliance_type="custom", id=id):
            await self._hset(name=name, key="workflow_status", value=str(workflow_status))
            if workflow_status == data_types.TemplateWorkflowStatus.PENDING:
                await self._hset(name=name, key="last_execution", value=datetime.now(UTC).isoformat())
        raise exceptions.ResourceNotFoundError(name=name)

    async def get_workflow_status(self, id: str) -> data_types.TemplateWorkflowStatus:
        name = self._appliance_name(id=id, index=self.CUSTOM_APPLIANCE_INDEX)
        if status := await self._get_decoded(name=name, key="workflow_status"):
            return data_types.TemplateWorkflowStatus(status)
        return data_types.TemplateWorkflowStatus.NEVER_RAN

    async def update_workflow_logs(self, id: str, logs: list[str], *, reset: bool = False) -> None:
        name = self._appliance_name(id=id, index=self.CUSTOM_APPLIANCE_INDEX)
        if await self.appliance_exists(appliance_type="custom", id=id):
            log_lines = "\n".join(logs)
            if reset:
                await self._hset(name=name, key="workflow_logs", value=log_lines)
            else:
                previous_logs = await self._get_decoded(name=name, key="workflow_logs")
                new_logs = f"{previous_logs}\n{log_lines}" if previous_logs else log_lines
                await self._hset(name=name, key="workflow_logs", value=new_logs)
        raise exceptions.ResourceNotFoundError(name=name)

    async def get_workflow_logs(self, id: str) -> str:
        name = self._appliance_name(id=id, index=self.CUSTOM_APPLIANCE_INDEX)
        if await self.appliance_exists(appliance_type="custom", id=id):
            if logs := await self._get_decoded(name=name, key="workflow_logs"):
                return logs
        return ""

    async def workflow_succeeded(self, id: str, volume_id: str) -> None:
        name = self._appliance_name(id=id, index=self.CUSTOM_APPLIANCE_INDEX)
        if await self.appliance_exists(appliance_type="custom", id=id):
            await self._hset(name=name, key="workflow_status", value=str(data_types.TemplateWorkflowStatus.SUCCEEDED))
            await self._hset(name=name, key="volume_id", value=volume_id)
        raise exceptions.ResourceNotFoundError(name=name)

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
    async def set_image(self, image_type: Literal["base"], config: models.BaseImageConfig) -> models.BaseImage: ...

    @overload
    async def set_image(self, image_type: Literal["custom"], config: models.CustomImageConfig) -> models.CustomImage: ...

    async def set_image(self, image_type: Literal["base", "custom"], config: models.BaseImageConfig | models.CustomImageConfig) -> models.BaseImage | models.CustomImage:
        index = self.BASE_IMAGE_INDEX if image_type == "base" else self.CUSTOM_IMAGE_INDEX
        name = self._image_name(id=config.id, index=index)
        config = await self._mutate_object(name=name, submitted=config)
        await self.client.sadd(index, config.id)
        if image_type == "base":
            state = await self._get_state(name=name, model=models.BaseImageState)
            return models.BaseImage(config=config, state=state)
        state = await self._get_state(name=name, model=models.CustomImageState)
        return models.CustomImage(config=config, state=state)
    
    @overload
    async def get_image(self, image_type: Literal["base"], id: str) -> models.BaseImage: ...

    @overload
    async def get_image(self, image_type: Literal["custom"], id: str) -> models.CustomImage: ...
    
    async def get_image(self, image_type: Literal["base", "custom"], id: str) -> models.BaseImage:
        index = self.BASE_IMAGE_INDEX if image_type == "base" else self.CUSTOM_IMAGE_INDEX
        name = self._image_name(id=id, index=index)
        model = models.BaseImageConfig if image_type == "base" else models.CustomImageConfig
        if config := await self._get_config(name=name, model=model):
            model = models.BaseImageState if image_type == "base" else models.CustomImageState
            state = await self._get_state(name=name, model=model)
            if isinstance(state, models.BaseImageState):
                return models.BaseImage(config=config, state=state)
            return models.CustomImage(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name)

    @overload
    async def list_images(self, image_type: Literal["base"]) -> list[models.BaseImage]: ...

    @overload
    async def list_images(self, image_type: Literal["custom"]) -> list[models.CustomImage]: ...

    async def list_images(self, image_type: Literal["base", "custom"]) -> list[models.BaseImage | models.CustomImage]:
        index = self.BASE_IMAGE_INDEX if image_type == "base" else self.CUSTOM_IMAGE_INDEX
        return [await self.get_image(image_type=image_type, id=id) for id in await self._list_set_members(index=index)]

    async def set_base_image_downloaded(self, id: str, volume_id: str) -> None:
        name = self._image_name(id=id, index=self.BASE_IMAGE_INDEX)
        await self._hset(name=name, key="volume_id", value=volume_id)
        await self._hset(name=name, key="download_date", value=datetime.now(UTC).isoformat())

    async def delete_image(self, image_type: Literal["base", "custom"], id: str) -> None:
        index = self.BASE_IMAGE_INDEX if image_type == "base" else self.CUSTOM_IMAGE_INDEX
        await self.client.delete(self._image_name(id=id, index=index))
        await self.client.srem(index, id)

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


class LXCClient(RedisClient):
    INDEX: Final = "ol:lxc:instances"

    def _instance_name(self, id: str) -> str:
        return f"{self.INDEX}:{id}"

    async def generate_instance_id(self) -> str:
        return await self._generate_unique_id(prefix="li", index=self.INDEX)

    async def instance_exists(self, id: str) -> bool:
        return id in await self._list_set_members(index=self.INDEX)

    async def set_instance(self, config: models.LXCInstanceConfig) -> None:
        if await self.instance_exists(id=config.id):
            raise exceptions.ResourceAlreadyExistsError(name=self._instance_name(id=config.id))
        name = self._instance_name(id=config.id)
        config = await self._mutate_object(name=name, submitted=config)
        await self.client.sadd(self.INDEX, config.id)

    async def set_instance_status(self, id: str, status: data_types.ComputeStatus) -> None:
        await self._hset(name=self._instance_name(id=id), key="status", value=str(status))

    async def set_instance_address(self, id: str, address: IPv4Address) -> None:
        await self._hset(name=self._instance_name(id=id), key="address", value=str(address))

    async def get_instance(self, id: str) -> models.LXCInstance:
        name = self._instance_name(id=id)
        if config := await self._get_config(name=name, model=models.LXCInstanceConfig):
            state = await self._get_state(name=name, model=models.LXCInstanceState)
            return models.LXCInstance(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name)

    async def list_instances(self) -> list[models.LXCInstance]:
        return [await self.get_instance(id=id) for id in await self._list_set_members(index=self.INDEX)]

    async def generate_lxc_create_params(self, id: str, vmid: int) -> dict:
        name = self._instance_name(id=id)
        if config := await self._get_config(name=name, model=models.LXCInstanceConfig):
            await self._hset(name=name, key="vmid", value=vmid)
            sector = await SectorClient().get(id=config.sector)
            return {
                "features": config.features,
                "ostemplate": config.volume_id,
                "hostname": config.id,
                "cores": config.cores,
                "memory": config.memory * 1024,
                "swap": config.memory * 1024,
                "net0": f"name=eth0,bridge={config.sector},ip=dhcp",
                "rootfs": f"{config.storage}:{config.disk_size}",
                "unprivileged": "0" if config.nfs else "1",
                "vmid": vmid,
                "password": await SecretsClient().get_lxc_password(lxc_id=id),
                "searchdomain": "sector.internal",
                "nameserver": f"{sector.config.dns_address.ip}",
                "onboot": "1",
            }
        raise exceptions.ResourceNotFoundError(name=name)

    async def delete_instance(self, id: str) -> None:
        await asyncio.gather(
            self.client.delete(self._instance_name(id=id)),
            SecretsClient().delete_lxc_password(lxc_id=id),
            self.client.srem(self.INDEX, id)
        )


class VMClient(RedisClient):
    INDEX: Final = "ol:vm:instances"

    def _instance_name(self, id: str) -> str:
        return f"{self.INDEX}:{id}"

    async def generate_instance_id(self) -> str:
        return await self._generate_unique_id(prefix="vi", index=self.INDEX)

    async def instance_exists(self, id: str) -> bool:
        return id in await self._list_set_members(index=self.INDEX)

    async def set_instance(self, config: models.VMInstanceConfig) -> None:
        if await self.instance_exists(id=config.id):
            raise exceptions.ResourceAlreadyExistsError(name=self._instance_name(id=config.id))
        name = self._instance_name(id=config.id)
        await self._mutate_object(name=name, submitted=config)
        await self.client.sadd(self.INDEX, config.id)

    async def set_instance_status(self, id: str, status: data_types.ComputeStatus) -> None:
        await self._hset(name=self._instance_name(id=id), key="status", value=str(status))

    async def set_instance_address(self, id: str, address: IPv4Interface) -> None:
        await self._hset(name=self._instance_name(id=id), key="address", value=str(address))

    async def get_instance(self, id: str) -> models.VMInstance:
        name = self._instance_name(id=id)
        if config := await self._get_config(name=name, model=models.VMInstanceConfig):
            state = await self._get_state(name=name, model=models.VMInstanceState)
            return models.VMInstance(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name)

    async def list_instances(self) -> list[models.VMInstance]:
        return [await self.get_instance(id=id) for id in await self._list_set_members(index=self.INDEX)]

    async def generate_vm_create_params(self, vmid: int, id: str) -> dict:
        name = self._instance_name(id=id)
        if config := await self._get_config(name=name, model=models.VMInstanceConfig):
            await self._hset(name=name, key="vmid", value=vmid)
            sector = await SectorClient().get(id=config.sector)
            return {
                "vmid": vmid,
                "name": config.id,
                "cores": config.cores,
                "sockets": config.sockets,
                "memory": config.memory * 1024,
                "cpu": "x86-64-v2-AES",
                "numa": 0,
                "agent": "enabled=1",
                "serial0": "socket",
                "scsi0": f"{config.storage}:0,import-from={config.volume_id}",
                "ide0": f"{config.storage}:cloudinit",
                "citype": "nocloud",
                "ciuser": config.user,
                "cipassword": await SecretsClient().get_vm_password(vm_id=id),
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

    async def delete_instance(self, id: str) -> None:
        await asyncio.gather(
            self.client.delete(self._instance_name(id=id)),
            SecretsClient().delete_vm_password(vm_id=id),
            self.client.srem(self.INDEX, id)
        )


class DataCoreClient(RedisClient):
    INDEX: Final = "ol:datacore:clusters"

    def _cluster_name(self, id: str) -> str:
        return f"{self.INDEX}:{id}"

    async def generate_cluster_id(self) -> str:
        return await self._generate_unique_id(prefix="dcc", index=self.INDEX)

    async def datacore_exists(self, id: str) -> bool:
        return id in await self._list_set_members(index=self.INDEX)

    async def set_datacore(self, config: models.DataCoreConfig) -> models.DataCore:
        name = self._cluster_name(id=config.id)
        config = await self._mutate_object(name=name, submitted=config)
        await self.client.sadd(self.INDEX, config.id)
        state = await self._get_state(name=name, model=models.DataCoreState)
        return models.DataCore(config=config, state=state)

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
                "application_user": config.application_user,
                "application_password": await secret_client.get_service_secret(service_name="datacore", service_id=id, subservice_name=config.application_user),
                "application_database": config.application_database,
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
                secret_client.delete_service_secret(service_name="datacore", service_id=id, subservice_name=config.application_user),
                self.client.delete(name)
            )


class DockFSClient(RedisClient):
    INDEX: Final = "ol:dockfs:clusters"

    def _cluster_name(self, id: str) -> str:
        return f"{self.INDEX}:{id}"

    async def generate_cluster_id(self) -> str:
        return await self._generate_unique_id(prefix="dfs", index=self.INDEX)

    async def cluster_exists(self, id: str) -> bool:
        return id in await self._list_set_members(index=self.INDEX)

    async def set_dockfs(self, config: models.DockFSConfig) -> models.DockFS:
        name = self._cluster_name(id=config.id)
        config = await self._mutate_object(name=name, submitted=config)
        await self.client.sadd(self.INDEX, config.id)
        state = await self._get_state(name=name, model=models.DockFSState)
        return models.DockFS(config=config, state=state)

    async def get_dockfs(self, id: str) -> models.DockFS:
        name = self._cluster_name(id=id)
        if config := await self._get_config(name=name, model=models.DockFSConfig):
            state = await self._get_state(name=name, model=models.DockFSState)
            return models.DockFS(config=config, state=state)
        raise exceptions.ResourceNotFoundError(name=name)

    async def list_dockfs_clusters(self) -> list[models.DockFS]:
        return [
            await self.get_dockfs(id=id) for id in await self._list_set_members(index=self.INDEX)
        ]

    async def generate_node_params(self, id: str, vmid: int, node_type: Literal["active", "passive"]) -> dict:
        name = self._cluster_name(id=id)
        if config := await self._get_config(name=name, model=models.DockFSConfig):
            state = await self._get_state(name=name, model=models.DockFSState)
            infra = await ClusterClient().get_infra_appliances()
            backplane = await BackplaneClient().get()
            address = await BackplaneClient().get_next_available_ip()
            hostname = await self._generate_unique_id(prefix=config.id, count=6, existing=state.node_names)
            params = {
                "vmid": vmid,
                "name": hostname,
                "cores": config.cores,
                "sockets": config.sockets,
                "memory": config.memory_gb * 1024,
                "cpu": "x86-64-v2-AES",
                "numa": 0,
                "agent": "enabled=1",
                "serial0": "socket",
                "scsi0": f"{config.storage}:0,import-from={infra.appliances['dockfs'].volume_id}",
                "ide0": f"{config.storage}:cloudinit",
                "citype": "nocloud",
                "ciuser": "root",
                "cipassword": await SecretsClient().get_service_secret(service_name="dockfs", service_id=id, subservice_name="password"),
                "net0": f"virtio,bridge={backplane.vnet_id}",
                "ipconfig0": f"ip={address},gw={backplane.default_gateway_address.ip}",
                "searchdomain": "orbitlab.internal",
                "nameserver": str(backplane.dns_address.ip),
                "scsihw": "virtio-scsi-single",
                "ostype": "l26",
                "onboot": "1",
                "boot": "order=scsi0",
            }
            if node_type == "active":
                params["scsi1"] = f"{config.storage}:{config.capacity_gb}"
            await self.set_node(id=id, node=models.DockFSNode(name=hostname, address=address, vmid=vmid), node_type=node_type)
            return params
        raise exceptions.ResourceNotFoundError(name=name)

    async def generate_config_command(self, id: str, node_type: Literal["active", "passive"]) -> str:
        name = self._cluster_name(id=id)
        if config := await self._get_config(name=name, model=models.DockFSConfig):
            command = "create" if node_type == "active" else "create-passive"
            auth_pass = await SecretsClient().get_service_secret(service_name="dockfs", service_id=id, subservice_name="password")
            return " ".join(["dockfs", command, str(config.vip), config.virtual_router_id, auth_pass])
        raise exceptions.ResourceNotFoundError(name=name)

    async def set_node(self, id: str, node: models.DockFSNode, node_type: Literal["active", "passive"]) -> None:
        await self._hset(name=self._cluster_name(id=id), key=node_type, value=node.model_dump_json())

    async def set_cluster_status(self, id: str, status: data_types.DockFSStatus) -> None:
        await self._hset(name=self._cluster_name(id=id), key="status", value=str(status))

    async def delete(self, id: str) -> None:
        await asyncio.gather(
            SecretsClient().get_service_secret(service_name="dockfs", service_id=id, subservice_name="auth_pass"),
            self.client.delete(self._cluster_name(id=id))
        )


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
            raise exceptions.ResourceAlreadyExistsError(name=self._get_redis_name(id=config.pool_name))
        name = self._get_redis_name(pool_name=config.pool_name)
        config = await self._mutate_object(name=name, submitted=config)
        await self.client.sadd(self.INDEX, config.pool_name)
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
