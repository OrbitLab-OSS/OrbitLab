
from datetime import UTC, datetime, timedelta
from functools import cached_property
import hashlib
from ipaddress import IPv4Interface, IPv4Network, IPv4Address
import json
from pathlib import Path
import re
from typing import Annotated, Final, Literal, Self

from cryptography import x509
from pydantic import BaseModel, Field, RootModel, SecretStr, computed_field, field_serializer, field_validator, model_serializer

from orbitlab import data_types


def _generate_mac(service_type: data_types.ServiceType, id: str) -> str:
    digest = hashlib.sha256(id.encode()).digest()
    mac_bytes = bytearray(6)
    mac_bytes[0] = 0x02
    mac_bytes[1] = data_types.ServiceType.get_mac_byte(service_type=service_type)
    mac_bytes[2:] = digest[:4]
    return ":".join(f"{b:02x}" for b in mac_bytes)


class Step(BaseModel):
    """Model for configuration steps in custom appliance creation."""

    type: Annotated[data_types.WorkflowStepType, data_types.SerializeEnum]
    name: str


SECRET_PATTERN = re.compile(
    r"@OL_SECRET\["
    r"(?P<name>[A-Za-z0-9/][A-Za-z0-9._/\-:]{0,191})"
    r"(?:@v(?P<version>[1-9][0-9]{0,8}))?"
    r"\]"
    r"(?:\[(?P<pointer>(?:/(?:[A-Za-z0-9._\-~]|~0|~1)*)*)\])?"
    r"@"
)


class ScriptStep(Step):
    """A configuration step that executes a script during custom appliance creation."""

    type: Annotated[data_types.WorkflowStepType, data_types.SerializeEnum] = data_types.WorkflowStepType.SCRIPT
    script: str
    
    @property
    def secret_injection_pattern(self) -> re.Pattern:
        return SECRET_PATTERN


class File(BaseModel):
    """Model for file push operations."""

    source: Annotated[Path, data_types.SerializePath]
    destination: Annotated[Path, data_types.SerializePath]


class FileStep(Step):
    """A configuration step that handles pushing files during custom appliance creation."""

    type: Annotated[data_types.WorkflowStepType, data_types.SerializeEnum] = data_types.WorkflowStepType.FILES
    files: list[File]


class ResourceConfig(BaseModel):
    version: int = 0
    last_update: int = 0  # unix timestamp of last update


class Controller(BaseModel):

    id: str = "orbitlab"
    asn: int = 65001
    peers: Annotated[list[IPv4Address], data_types.SerializeIPList]
    
    @property
    def peer_list(self) -> str:
        return ",".join([str(peer) for peer in self.peers])


class BackplaneConfig(ResourceConfig):
    zone_id: str = "orbitlab"
    vnet_id: str = "orbitlab"
    controller: Controller
    zone_tag: int
    vnet_tag: int
    mtu: int
    cidr_block: Annotated[IPv4Network, data_types.SerializeIP]
    exit_nodes: list[str]

    @property
    def default_gateway(self) -> IPv4Interface:
        return IPv4Interface(f"{self.cidr_block.network_address + 1}/{self.cidr_block.prefixlen}")

    @property
    def dns_address(self) -> IPv4Interface:
        return IPv4Interface(f"{self.cidr_block.network_address + 2}/{self.cidr_block.prefixlen}")

    @property
    def orbital_relay_address(self) -> IPv4Interface:
        return IPv4Interface(f"{self.cidr_block.network_address + 3}/{self.cidr_block.prefixlen}")


class BackplaneState(BaseModel):
    status: Annotated[data_types.BackplaneStatus, data_types.SerializeEnum] = data_types.BackplaneStatus.PENDING
    version: str = ""


class Backplane(BaseModel):
    config: BackplaneConfig
    state: BackplaneState


class InfraAppliance(BaseModel):
    """OrbitLab Infrastructure Appliance."""

    node: str
    volume_id: str
    
    @property
    def filename(self) -> str:
        return self.volume_id.split("/")[-1]
    
    @property
    def storage(self) -> str:
        return self.volume_id.split(":")[0]


class InfraAppliances(BaseModel):
    appliances: dict[data_types.OrbitLabApplianceType, InfraAppliance]
    version: str
    
    def add(self, appliance_type: data_types.OrbitLabApplianceType, appliance: InfraAppliance) -> None:
        self.appliances[appliance_type] = appliance

    @classmethod
    def empty(cls) -> Self:
        return cls(appliances={}, version="")


class Defaults(BaseModel):
    """Default configuration settings for the cluster."""

    node: str
    vztmpl: str
    imports: str
    rootdir: str
    images: str
    snippets: str = Field(default="")
    iso: str = Field(default="")
    backup: str = Field(default="")
    
    @classmethod
    def empty(cls) -> Self:
        return cls(node="", vztmpl="", imports="", rootdir="", images="")
    
    def valid(self) -> str:
        for required_field in ("node", "vztmpl", "imports", "rootdir", "images"):
            if not getattr(self, required_field):
                return required_field
        return ""


class DomainProvider(BaseModel):
    name: str
    provider: Annotated[data_types.DomainValidationProviders, data_types.SerializeEnum]
    email: str
    credentials: str


class DomainProviders(BaseModel):
    providers: list[DomainProvider]


class ETCDMember(BaseModel):
    """Represents an ETCD cluster member."""

    vmid: int = 0
    name: str
    address: Annotated[IPv4Interface, data_types.SerializeIP]


class SectorDomain(BaseModel):
    domain: str
    domain_provider: str

    @property
    def cert_resolver(self) -> str:
        yaml_format = self.domain.replace(".", "-")
        return f"{self.domain_provider}-{yaml_format}"


class SectorConfiguration(ResourceConfig):
    cidr_block: Annotated[IPv4Network, data_types.SerializeIP]
    alias: str
    tag: int
    backplane_address: Annotated[IPv4Interface, data_types.SerializeIP]
    storage: str
    domains: list[SectorDomain] = Field(default_factory=list)
    
    @computed_field
    @property
    def id(self) -> str:
        return f"olvn{self.tag}"
    
    @property
    def bridge(self) -> str:
        return self.id

    @property
    def default_gateway(self) -> IPv4Interface:
        """Get the primary gateway interface for this sector."""
        return IPv4Interface(f"{self.cidr_block.network_address + 1}/{self.cidr_block.prefixlen}")

    @property
    def dns_address(self) -> IPv4Interface:
        """Get the DNS IP address for this sector."""
        return IPv4Interface(f"{self.cidr_block.network_address + 2}/{self.cidr_block.prefixlen}")

    @property
    def conduit_internal_mac(self) -> str:
        return _generate_mac(service_type=data_types.ServiceType.CONDUIT, id=self.id)

    @property
    def conduit_external_mac(self) -> str:
        return _generate_mac(service_type=data_types.ServiceType.CONDUIT, id=f"{self.id}-external")

    @property
    def wardlink_internal_mac(self) -> str:
        return _generate_mac(service_type=data_types.ServiceType.WARDLINK, id=self.id)

    @property
    def wardlink_external_mac(self) -> str:
        return _generate_mac(service_type=data_types.ServiceType.WARDLINK, id=f"{self.id}-external")

    @property
    def configured_domains(self) -> list[str]:
        return [domain.domain for domain in self.domains]

    def add_domain(self, domain: str, domain_provider: str) -> None:
        self.domains.append(SectorDomain(domain=domain, domain_provider=domain_provider))


class SectorVIP(BaseModel):
    """Sector VIP Assignment."""

    virtual_router_id: int
    address: Annotated[IPv4Interface, data_types.SerializeIP]


class WardLinkClient(BaseModel):
    index: int
    name: str
    address: Annotated[IPv4Interface, data_types.SerializeIP]
    secret: str


class SectorState(BaseModel):
    vips: dict[int, Annotated[IPv4Interface, data_types.SerializeIP]] = Field(default_factory=dict)
    gateway_vmid: int = 0
    conduit_vmid: int = 0
    wardlink_vmid: int = 0
    gateway_version: str = ""
    conduit_version: str = ""
    wardlink_version: str = ""
    gateway_status: Annotated[data_types.SectorStatus, data_types.SerializeEnum] = data_types.SectorStatus.PENDING
    conduit_status: Annotated[data_types.ConduitStatus, data_types.SerializeEnum] = data_types.ConduitStatus.ABSENT
    wardlink_status: Annotated[data_types.WardLinkStatus, data_types.SerializeEnum] = data_types.WardLinkStatus.ABSENT
    wardlink_cidr: Annotated[IPv4Network, data_types.SerializeIP] | None = None
    wardlink_clients: dict[str, WardLinkClient] = Field(default_factory=dict)

    @field_validator("vips", "wardlink_clients", mode="before")
    @classmethod
    def parse_node(cls, value: str | None) -> dict[int, str]:
        if value:
            return json.loads(value)
        return {}


RESERVED_SECTOR_IP_COUNT: Final = 50

class Sector(BaseModel):
    config: SectorConfiguration
    state: SectorState
    
    def get_cert_resolver(self, domain: str) -> str:
        if sector_domain := next(iter([sd for sd in self.config.domains if sd.domain == domain]), None):
            return sector_domain.cert_resolver
        msg = f"Cert resolver for {domain} not found"
        raise ValueError(msg)
    
    def get_available_vip(self) -> SectorVIP:
        used_vrids = list(self.state.vips.keys())
        used_vips = [address.ip for address in self.state.vips.values()]
        vrid = next(iter(i for i in range(1,256) if i not in used_vrids))
        # First two are Default GW and DNS, respectively
        useable = list(self.config.cidr_block.hosts())[2:RESERVED_SECTOR_IP_COUNT]
        address = next(addr for addr in useable if addr not in used_vips)
        return SectorVIP(virtual_router_id=vrid, address=IPv4Interface(f"{address}/{self.config.cidr_block.prefixlen}"))
    
    def get_new_wardlink_client_address(self) -> IPv4Interface:
        if self.state.wardlink_cidr:
            used = [self.state.wardlink_cidr.network_address + 1]
            used.extend([client.address.ip for client in self.state.wardlink_clients.values()])
            address = next(addr for addr in self.state.wardlink_cidr.hosts() if addr not in used)
            return IPv4Interface(f"{address}/{self.state.wardlink_cidr.prefixlen}")
        msg = f"Sector {self.config.id} WardLink CIDR not set"
        raise ValueError(msg)


class ARecord(BaseModel):
    
    ip: Annotated[IPv4Address, data_types.SerializeIP]
    ttl: int = 300


class ARecords(BaseModel):
    a: list[ARecord] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return bool(self.a)

    def add(self, *records: ARecord) -> None:
        self.a.extend(list(records))

    def remove(self, *records: ARecord) -> None:
        self.a = [record for record in self.a if record not in records]


class SRVRecord(BaseModel):
    target: str
    port: int
    priority: int = 0
    weight: int = 0
    ttl: int = 300


class SRVRecords(BaseModel):
    srv: list[SRVRecord] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return bool(self.srv)

    def add(self, *records: SRVRecord) -> None:
        self.srv.extend(list(records))

    def remove(self, *records: SRVRecord) -> None:
        self.srv = [record for record in self.srv if record not in records]


class ZoneDefinitionRecords(BaseModel):
    zone: str
    refresh: int = 3600
    retry: int = 900
    expire: int = 1209600
    ttl: int = 300

    @model_serializer(mode="plain")
    def to_redis_record(self) -> dict:
        soa = {
            "mbox": f"admin.{self.zone}", "ns": f"ns.{self.zone}", "refresh": self.refresh, "retry": self.retry, "expire": self.expire, "ttl": self.ttl
        }
        ns = {"host": f"ns.{self.zone}", "ttl": self.ttl}
        return {"soa": soa, "ns": ns}


class SecretMetadata(BaseModel):
    previous_versions: set[int] = Field(default_factory=set)


class Secret(ResourceConfig):
    name: str
    created_at: datetime
    description: str
    metadata: SecretMetadata
    secret_version: int
    last_rotation: datetime | None = Field(default=None)
    secret_string: SecretStr

    @field_serializer("secret_string", when_used="json")
    def dump_secret(self, secret_string: SecretStr) -> str:
        """Serialize the secret string for JSON output.

        Args:
            secret_string (SecretStr): The secret value to serialize.

        Returns:
            str: The plain secret string value.
        """
        return secret_string.get_secret_value()

    @classmethod
    def create(cls, secret_name: str, value: str, description: str) -> Self:
        return cls(
            name=secret_name,
            created_at=datetime.now(UTC),
            description=description,
            metadata=SecretMetadata(),
            secret_version=1,
            secret_string=SecretStr(value),
        )

    def rotate(self, new_value: str) -> None:
        self.metadata.previous_versions.add(self.secret_version)
        self.secret_string = SecretStr(new_value)
        self.secret_version += 1
        self.last_rotation = datetime.now(UTC)


class Subject(BaseModel):
    """Represents the subject information for an X.509 certificate."""

    common_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.\-\* ]{1,64}(?:\.[A-Za-z0-9_.\-\* ]{1,64})*$")]
    org: Annotated[str, Field(pattern=r"[A-Za-z0-9 .,'()\-_/&]{1,128}")]
    org_unit: Annotated[str, Field(pattern=r"[A-Za-z0-9 .,'()\-_/&]{1,128}")]
    country: Annotated[str, Field(pattern=r"[A-Z]{2}")]
    state_or_province: Annotated[str, Field(pattern=r"[A-Za-z0-9 .,'()\-_/&]{1,128}")]
    locality: Annotated[str, Field(pattern=r"[A-Za-z0-9 .,'()\-_/&]{1,128}")]

    def to_x509(self) -> x509.Name:
        """Convert the Subject instance to a cryptography.x509.Name object.

        Returns:
            x509.Name: The X.509 Name representation of the subject.
        """
        return x509.Name(
            [
                x509.NameAttribute(x509.NameOID.COUNTRY_NAME, self.country),
                x509.NameAttribute(x509.NameOID.STATE_OR_PROVINCE_NAME, self.state_or_province),
                x509.NameAttribute(x509.NameOID.LOCALITY_NAME, self.locality),
                x509.NameAttribute(x509.NameOID.ORGANIZATION_NAME, self.org),
                x509.NameAttribute(x509.NameOID.ORGANIZATIONAL_UNIT_NAME, self.org_unit),
                x509.NameAttribute(x509.NameOID.COMMON_NAME, self.common_name),
            ],
        )


class Certificate(BaseModel):
    subject: Subject
    issuer: str
    not_before: datetime
    not_after: datetime
    certificate: data_types.CertificateData
    fingerprint: str
    serial_number: str
    key_usage: Annotated[list[data_types.KeyUsageTypes], data_types.SerializeEnumList]

    @property
    def status(self) -> Literal["valid", "warning", "expired"]:
        """Return the current status of the certificate based on its validity period."""
        if self.not_after < datetime.now(UTC):
            return "expired"
        if self.not_after - timedelta(days=30) < datetime.now(UTC):
            return "warning"
        return "valid"  


class RootCert(Certificate):
    """Root Cert"""
    

class IntermediateCert(Certificate):
    domain_constraint: str
    chain: data_types.CertificateData


class LeafCert(Certificate):
    san_dns: list[str]
    san_ips: list[str]
    chain: data_types.CertificateData


class SSHKey(BaseModel):
    public_key: str
    fingerprint: str
    key_type: Annotated[data_types.SSHKeyTypes, data_types.SerializeEnum]


class NodeConfig(ResourceConfig):
    name: str
    address:  Annotated[IPv4Address, data_types.SerializeIP]
    proxmox_version: str
    

class NodeState(BaseModel):
    online: bool = False
    maintenance_mode: bool = False


class Node(BaseModel):
    config: NodeConfig
    state: NodeState


class BaseApplianceConfig(ResourceConfig):
    id: str
    node: str
    storage: str
    template: str
    oci: bool = False
    description: str = ""


class BaseApplianceState(BaseModel):
    volume_id: str = ""
    download_date: datetime | None = None
    
    @property
    def filename(self) -> str:
        return self.volume_id.split("/")[-1]
    
    @property
    def storage(self) -> str:
        return self.volume_id.split(":")[0]


class BaseAppliance(BaseModel):
    config: BaseApplianceConfig
    state: BaseApplianceState


class CustomApplianceConfig(ResourceConfig):
    id: str
    name: str
    node: str
    base_appliance_id: str
    base_volume_id: str
    disk_store: str
    storage: str
    cores: int
    memory: int
    swap: int
    sector: str
    created_on: datetime = datetime.now(UTC)
    steps: list[FileStep | ScriptStep] = Field(default_factory=list)

    def workflow_create_params(self, vmid: int, password: str, sector_dns: IPv4Address) -> dict:
        return {
            "features": "nesting=1",
            "cores": self.cores,
            "unprivileged": "1",
            "onboot": "0",
            "vmid": vmid,
            "memory": f"{self.memory * 1024}",
            "swap": f"{self.swap * 1024}",
            "ostemplate": self.base_volume_id,
            "hostname": f"wf-{self.id}",
            "rootfs": f"{self.disk_store}:8",
            "password": password,
            "net0": f"name=eth0,bridge={self.sector},ip=dhcp",
            "searchdomain": "sector.internal",
            "nameserver": str(sector_dns),
        }


class CustomApplianceState(BaseModel):
    volume_id: str = ""
    last_execution: datetime | None = None
    workflow_status: Annotated[data_types.TemplateWorkflowStatus, data_types.SerializeEnum] = data_types.TemplateWorkflowStatus.NEVER_RAN


class CustomAppliance(BaseModel):
    config: CustomApplianceConfig
    state: CustomApplianceState


class BaseImageConfig(ResourceConfig):
    id: str
    node: str
    filename: str
    storage: str
    checksum_algorithm: str
    checksum: str
    os: str
    build_date: str
    download_url: str


class BaseImageState(BaseModel):
    volume_id: str = ""
    download_date: datetime | None = None


class BaseImage(BaseModel):
    config: BaseImageConfig
    state: BaseImageState


class CustomImageConfig(ResourceConfig):
    id: str
    name: str
    base_image_id: str
    base_volume_id: str
    node: str
    disk_storage: str
    disk_size: int
    storage: str
    memory: int
    cores: int
    sector: str
    created_on: datetime = datetime.now(UTC)
    steps: list[FileStep | ScriptStep] = Field(default_factory=list)

    def workflow_create_params(self, vmid: int, password: str, sector_dns: IPv4Address) -> dict:
        return {
            "vmid": vmid,
            "name": f"wf-{self.id}",
            "cores": self.cores,
            "sockets": "1",
            "memory": self.memory * 1024,
            "cpu": "x86-64-v2-AES",
            "numa": 0,
            "agent": "enabled=1",
            "serial0": "socket",
            "scsi0": f"{self.disk_storage}:0,import-from={self.base_volume_id}",
            "ide0": f"{self.disk_storage}:cloudinit",
            "citype": "nocloud",
            "ciuser": "root",
            "ciupgrade": "0",
            "cipassword": password,
            "net0": f"virtio,bridge={self.sector}",
            "ipconfig0": "ip=dhcp",
            "searchdomain": "sector.internal",
            "nameserver": str(sector_dns),
            "scsihw": "virtio-scsi-single",
            "ostype": "l26",
            "onboot": "0",
            "boot": "order=scsi0",
        }


class CustomImageState(BaseModel):
    volume_id: str = ""
    last_execution: datetime | None = None
    workflow_status: Annotated[data_types.TemplateWorkflowStatus, data_types.SerializeEnum] = data_types.TemplateWorkflowStatus.NEVER_RAN


class CustomImage(BaseModel):
    config: CustomImageConfig
    state: CustomImageState


class InstanceConfig(ResourceConfig):
    type: Literal["lxc", "qemu"]
    id: str
    name: str
    base_id: str
    volume_id: str
    storage: str
    disk_size: int
    sector: str
    memory: int
    cores: int
    sector_name: str
    node: str
    
    # LXC Specific
    swap: int = 512
    nfs: bool = False
    
    # VM Specific
    sockets: int = 1
    user: str = "root"
    
    @property
    def features(self) -> str:
        features = "nesting=1"
        if self.nfs:
            features += ",mount=nfs"
        return features
    
    @computed_field
    @property
    def mac(self) -> str:
        return _generate_mac(service_type=data_types.ServiceType.INSTANCE, id=self.id)

    @computed_field(repr=False)
    @property
    def vcpus(self) -> int:
        return self.cores * self.sockets


class InstanceState(BaseModel):
    vmid: int = 0
    status: Annotated[data_types.ComputeStatus, data_types.SerializeEnum] = data_types.ComputeStatus.PENDING
    address: Annotated[IPv4Address, data_types.SerializeIP] | None = None


class Instance(BaseModel):
    config: InstanceConfig
    state: InstanceState


class DataCoreConfig(ResourceConfig):
    id: str
    name: str
    rw_virtual_router_id: int = Field(ge=1, le=255)
    ro_virtual_router_id: int = Field(ge=1, le=255)
    rw_vip: Annotated[IPv4Interface, data_types.SerializeIP]
    ro_vip: Annotated[IPv4Interface, data_types.SerializeIP]
    replicas: int
    memory_gb: int
    cores: int
    capacity_gb: int
    storage: str
    sector: str
    sector_name: str


class DataCoreNode(BaseModel):
    """Represents a DataCore cluster node with VM ID and name."""

    vmid: int
    name: str
    role: str = ""
    online: bool = False


class DataCoreNodes(RootModel[list[DataCoreNode]]):

    def _change_node_state(self, name: str, *, online: bool, role: str) -> None:
        for node in self.root:
            if node.name == name:
                node.online = online
                node.role = role
                return
        msg = f"Node with name {name} not found."
        raise ValueError(msg)

    def set_node_online(self, name: str, role: data_types.DataCoreNodeRole) -> None:
        self._change_node_state(name=name, online=True, role=str(role))

    def set_node_offline(self, name: str, role: data_types.DataCoreNodeRole) -> None:
        self._change_node_state(name=name, online=False, role=str(role))

    def set_node_role(self, name: str, role: data_types.DataCoreNodeRole) -> None:
        self._change_node_state(name=name, online=True, role=str(role))

    @property
    def healthy(self) -> bool:
        return all([node.online for node in self.root])
    
    @property
    def degraded(self) -> bool:
        return any([node.online for node in self.root])


class DataCoreState(BaseModel):
    nodes: DataCoreNodes = DataCoreNodes(root=[])
    status: Annotated[data_types.DataCoreStatus, data_types.SerializeEnum] = data_types.DataCoreStatus.PENDING

    @field_validator("nodes", mode="before")
    @classmethod
    def parse_nodes(cls, value: str | None) -> DataCoreNodes | None:
        if value:
            return DataCoreNodes.model_validate_json(value)
        return None


class DataCore(BaseModel):
    config: DataCoreConfig
    state: DataCoreState


class DockFSConfig(ResourceConfig):
    id: str
    name: str
    virtual_router_id: int = Field(ge=1, le=255)
    vip: Annotated[IPv4Interface, data_types.SerializeIP]
    memory: int
    sockets: int
    sector: str
    sector_name: str
    cores: int
    capacity_gb: int
    storage: str
    
    @computed_field
    @property
    def vcpus(self) -> int:
        return self.sockets * self.cores

    @classmethod
    def generate_mac(cls, hostname: str) -> str:
        return _generate_mac(service_type=data_types.ServiceType.DOCKFS, id=hostname)


class DockFSNode(BaseModel):
    name: str
    address: Annotated[IPv4Interface, data_types.SerializeIP] | None = None
    mac: str
    vmid: int


class DockFSState(BaseModel):
    status: Annotated[data_types.DockFSStatus, data_types.SerializeEnum] = data_types.DockFSStatus.PENDING
    active: DockFSNode | None = None
    passive: DockFSNode | None = None

    @property
    def cluster_nodes(self) -> list[DockFSNode]:
        nodes = [self.active, self.passive]
        return [node for node in nodes if node]

    @property
    def node_names(self) -> list[str]:
        return [node.name for node in self.cluster_nodes]

    @field_validator("active", "passive", mode="before")
    @classmethod
    def parse_node(cls, value: str | None) -> DockFSNode | None:
        if value:
            return DockFSNode.model_validate_json(value)
        return None


class DockFS(BaseModel):
    config: DockFSConfig
    state: DockFSState

    def get_node_by_mac(self, mac: str) -> tuple[Literal["active", "passive"], DockFSNode] | tuple[None, None]:
        node = next(iter([node for node in self.state.cluster_nodes if node.mac == mac]), None)
        if not node:
            return None, None
        if self.state.active == node:
            return "active", node
        return "passive", node


class ComputeConfig(BaseModel):
    cores: int
    memory_gb: int
    disk_size: int
    storage: str
    volume_id: str
    

class VMConfig(ComputeConfig):
    type: Literal["vm"]
    sockets: int


class LXCConfig(ComputeConfig):
    type: Literal["lxc"]
    swap_mb: int


class InstanceTarget(BaseModel):
    instance_id: str
    weight: int | None = None
    
    def generate_server_url(self, port: int) -> str:
        return f"http://{self.instance_id}.sector.internal:{port}"


class HealthCheck(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH"] = "GET"
    path: str = "/"
    expected_status: int = 200
    interval: int = 30
    timeout: int = 5
    port: int | None = None

    def generate_config_commands(self, prefix: str) -> str:
        commands = [
            f"etcdctl put {prefix}/healthcheck/method '{self.method}'",
            f"etcdctl put {prefix}/healthcheck/path '{self.path}'",
            f"etcdctl put {prefix}/healthcheck/interval '{self.interval}s'",
            f"etcdctl put {prefix}/healthcheck/timeout '{self.timeout}s'",
            f"etcdctl put {prefix}/healthcheck/status {self.expected_status}",
        ]
        if self.port is not None:
            commands.append(f"etcdctl put {prefix}/healthcheck/port {self.port}")
        else:
            commands.append(f"etcdctl del {prefix}/healthcheck/port")
        return "\n".join(commands)


class ConduitPoolConfig(ResourceConfig):
    id: str
    type: data_types.ConduitEndpointType
    name: str
    sector: str
    sector_name: str
    targets: list[InstanceTarget]
    port: int
    health_check: HealthCheck
    balance: str


class ConduitPoolState(BaseModel):
    associated_endpoints: list[str] = Field(default_factory=list)
    targets_health: dict[str, str] = Field(default_factory=dict)
    
    @computed_field
    @property
    def health(self) -> Literal["Unused", "Healthy", "Degraded", "Unhealthy"]:
        if len(self.associated_endpoints) == 0:
            return "Unused"
        if all([status == "UP" for status in self.targets_health.values()]):
            return "Healthy"
        if all([status == "DOWN" for status in self.targets_health.values()]):
            return "Unhealthy"
        return "Degraded"

    @field_validator("associated_endpoints", mode="before")
    @classmethod
    def serialize_associated_endpoints(cls, value: list | str) -> list:
        if isinstance(value, list):
            return value
        return json.loads(value)
    
    @field_validator("targets_health", mode="before")
    @classmethod
    def serialize_target_health(cls, value: dict | str) -> dict:
        if isinstance(value, dict):
            return value
        return json.loads(value)


class ConduitPool(BaseModel):
    config: ConduitPoolConfig
    state: ConduitPoolState
    
    @cached_property
    def prefix(self) -> str:
        return f"conduit-{self.config.sector}/{self.config.type}/services/{self.config.id}/loadbalancer"
    
    def generate_config_commands(self) -> str:
        commands = "\n".join([
            f"etcdctl put {self.prefix}/servers/{index}/url '{target.generate_server_url(port=self.config.port)}'"
            for index, target in enumerate(self.config.targets)
        ])
        commands += f"\netcdctl put {self.prefix}/strategy '{self.config.balance}'"
        commands += f"\n{self.config.health_check.generate_config_commands(prefix=self.prefix)}"
        return commands


class RouterRule(BaseModel):
    host: str = ""
    path: str = ""
    
    def to_rule(self) -> str:
        if self.host:
            return f"Host(`{self.host}`)"
        if self.path:
            return f"Path(`{self.path}`)"
        msg = "Neither host nor path is set"
        raise ValueError(msg)


class ConduitEndpointConfig(ResourceConfig):
    id: str
    name: str
    domain: str
    type: data_types.ConduitEndpointType
    sector: str
    sector_name: str
    port: int
    pool: str
    pool_name: str
    rules: list[RouterRule]
    
    @cached_property
    def prefix(self) -> str:
        type = "http" if "http" in self.type else self.type
        return f"conduit-{self.sector}/{type}/routers"
    
    def generate_config_commands(self, cert_resolver: str) -> str:
        rule = " || ".join([rule.to_rule() for rule in self.rules])
        commands = [
            f"etcdctl del {self.prefix}/{self.id}-http",
            f"etcdctl del {self.prefix}/{self.id}-https",
        ]
        if self.type == "http":
            commands = [
                f"etcdctl put {self.prefix}/{self.id}-http/rule '{rule}'",
                f"etcdctl put {self.prefix}/{self.id}-http/service '{self.pool}'",
                f"etcdctl put {self.prefix}/{self.id}-http/entrypoints/0 'web'"
            ]
        elif self.type == "https":
            commands = [
                f"etcdctl put {self.prefix}/{self.id}-http/rule '{rule}'",
                f"etcdctl put {self.prefix}/{self.id}-http/service 'noop@internal'",
                f"etcdctl put {self.prefix}/{self.id}-http/entrypoints/0 'web'",
                f"etcdctl put {self.prefix}/{self.id}-http/middlewares/0 'http-redirect'",
                f"etcdctl put {self.prefix}/{self.id}-https/rule '{rule}'",
                f"etcdctl put {self.prefix}/{self.id}-https/service '{self.pool}'",
                f"etcdctl put {self.prefix}/{self.id}-https/entrypoints/0 'websecure'",
                f"etcdctl put {self.prefix}/{self.id}-https/tls/certresolver 'websecure'",
            ]
        return "\n".join(commands)


# UP // UP X/Y // MAINT (resolution)  // DOWN // DOWN X/Y
class ConduitEndpointState(BaseModel):
    listener_address: Annotated[IPv4Address, data_types.SerializeIP] | None = None


class ConduitEndpoint(BaseModel):
    config: ConduitEndpointConfig
    state: ConduitEndpointState


class AutoscalingPoolConfiguration(ResourceConfig):
    pool_name: str
    sector: str
    sector_name: str
    compute_config:  VMConfig | LXCConfig = Field(discriminator="type")
    desired_count: int
    health_check: HealthCheck

    @property
    def secret_name(self) -> str:
        return f"/orbitlab/autoscaling/{self.pool_name}"


class AutoscalingPoolState(BaseModel):
    warmup: bool = False
    cooldown: bool = False


class AutoscalingPool(BaseModel):
    config: AutoscalingPoolConfiguration
    state: AutoscalingPoolState
