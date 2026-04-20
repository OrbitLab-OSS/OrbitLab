
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Interface, IPv4Network, IPv4Address
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography import x509
from pydantic import BaseModel, Field, RootModel, SecretStr, computed_field, field_serializer, model_serializer

from orbitlab import constants
from orbitlab import data_types


class Step(BaseModel):
    """Model for configuration steps in custom appliance creation."""

    type: Annotated[data_types.WorkflowStepType, data_types.SerializeEnum]
    name: str


class ScriptStep(Step):
    """A configuration step that executes a script during custom appliance creation."""

    type: Annotated[data_types.WorkflowStepType, data_types.SerializeEnum] = data_types.WorkflowStepType.SCRIPT
    script: str


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

    id: str
    asn: int
    peers: Annotated[list[IPv4Address], data_types.SerializeIPList]


class Backplane(ResourceConfig):
    zone_id: str
    vnet_id: str
    controller: Controller
    zone_tag: int
    vnet_tag: int
    mtu: int
    cidr_block: Annotated[IPv4Network, data_types.SerializeIP]
    default_gateway_address: Annotated[IPv4Interface, data_types.SerializeIP]
    dns_address: Annotated[IPv4Interface, data_types.SerializeIP]
    orbital_relay_address: Annotated[IPv4Interface, data_types.SerializeIP]
    reserved_tags: list[int]

    @property
    def peer_list(self) -> str:
        return ",".join([str(peer) for peer in self.controller.peers])


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


class Defaults(BaseModel):
    """Default configuration settings for the cluster."""

    node: str
    vztmpl: str
    imports: str
    rootdir: str
    snippets: str = Field(default="")
    iso: str = Field(default="")
    backup: str = Field(default="")
    images: str = Field(default="")


class Cluster(ResourceConfig):
    nodes: list[str]
    initialized: bool

    @property
    def exit_nodes(self) -> str:
        return ",".join(self.nodes)


class ETCDMember(BaseModel):
    """Represents an ETCD cluster member."""

    vmid: int = 0
    name: str
    address: Annotated[IPv4Interface, data_types.SerializeIP]


class SectorConfiguration(ResourceConfig):
    id: str
    cidr_block: Annotated[IPv4Network, data_types.SerializeIP]
    alias: str
    tag: int
    backplane_address: Annotated[IPv4Interface, data_types.SerializeIP]
    storage: str
    
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


class SectorVIP(BaseModel):
    """Sector VIP Assignment."""

    virtual_router_id: int
    address: Annotated[IPv4Interface, data_types.SerializeIP]


class SectorState(BaseModel):
    vips: dict[int, Annotated[IPv4Interface, data_types.SerializeIP]] = Field(default_factory=dict)
    gateway_vmid: int = 0
    gateway_version: str = ""
    status: Annotated[data_types.SectorStatus, data_types.SerializeEnum] = data_types.SectorStatus.PENDING


class Sector(BaseModel):
    config: SectorConfiguration
    state: SectorState
    
    def get_available_vip(self) -> SectorVIP:
        used_vrids = list(self.state.vips.keys())
        used_vips = list(self.state.vips.values())
        vrid = next(iter(i for i in range(1,256) if i not in used_vrids))
        # First two are Default GW and DNS, respectively
        useable = list(self.config.cidr_block.hosts())[2:constants.NetworkSettings.RESERVED_SECTOR_IPS]
        address = next(iter(addr for addr in useable if addr not in used_vips))
        return SectorVIP(virtual_router_id=vrid, address=IPv4Interface(f"{address}/{self.config.cidr_block.prefixlen}"))

    # def generate_gateway_params(self) -> dict[str, str]:
    #     if not self.state.gateway_vmid:
    #         raise SectorConfigurationError(sector=self.bridge, message="Gateway VMID not set.")
    #     return {
    #         "features": "nesting=1",
    #         "ostemplate": self.config.gateway_appliance,
    #         "hostname": f"{self.bridge}-gw",
    #         "cores": "1",
    #         "memory": "512",
    #         "swap": "512",
    #         "net0": f"name=eth0,bridge={self.bridge},ip={self.default_gateway}",
    #         "net1": (
    #             "name=eth1,"
    #             f"bridge={self.config.backplane_vnet_id},"
    #             f"ip={self.config.backplane_address},"
    #             f"gw={self.config.backplane_default_gw}"
    #         ),
    #         "net2": f"name=eth2,bridge={self.bridge},ip={self.dns_address}",
    #         "rootfs": f"{self.config.storage}:8",
    #         "unprivileged": "1",
    #         "vmid": self.state.gateway_vmid,
    #         "password": SecretVault.generate_random_password(),
    #         "searchdomain": "sector.internal",
    #         "nameserver": str(self.config.backplane_dns),
    #         "onboot": "1",
    #     }


class ARecord(BaseModel):
    
    address: Annotated[IPv4Address, data_types.SerializeIP]
    ttl: int = 300

    @model_serializer(mode="plain")
    def to_redis_record(self) -> dict:
        return {"ip4": str(self.address), "ttl": self.ttl}


class ARecords(BaseModel):
    a: list[ARecord] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return bool(self.a)


class SRVRecord(BaseModel):
    host: str
    port: int
    priority: int = 0
    weight: int = 0
    ttl: int = 300

    @model_serializer(mode="plain")
    def to_redis_record(self) -> dict:
        if not self.host.endswith("orbitlab.internal"):
            self.host = f"{self.host}.orbitlab.internal"
        return {
            "host": self.host, "port": self.port, "priority": self.priority, "weight": self.weight, "ttl": self.ttl
        }


class SRVRecords(BaseModel):
    srv: list[SRVRecord] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return bool(self.srv)


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
            secret_string=value,
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
    volume_id: str
    storage: str
    cores: int
    memory: int
    swap: int
    sector: str
    created_on: datetime = datetime.now(UTC)
    steps: list[FileStep | ScriptStep] = Field(default_factory=list)

    def workflow_create_params(self, vmid: str, password: str, sector_dns: IPv4Address) -> dict:
        return {
            "features": "nesting=1",
            "cores": self.cores,
            "unprivileged": "1",
            "onboot": "0",
            "vmid": vmid,
            "memory": f"{self.memory * 1024}",
            "swap": f"{self.swap * 1024}",
            "ostemplate": self.volume_id,
            "hostname": f"wf-{self.id}",
            "rootfs": f"{self.storage}:8",
            "password": password,
            "net0": f"name=eth0,bridge={self.sector},ip=dhcp",
            "searchdomain": "sector.internal",
            "nameserver": str(sector_dns),
        }


class CustomApplianceState(BaseModel):
    volume_id: str = ""
    last_execution: datetime | None = None
    worflow_status: Annotated[data_types.TemplateWorkflowStatus, data_types.SerializeEnum] = data_types.TemplateWorkflowStatus.NEVER_RAN


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
    image_storage: str
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
    worflow_status: Annotated[data_types.TemplateWorkflowStatus, data_types.SerializeEnum] = data_types.TemplateWorkflowStatus.NEVER_RAN


class CustomImage(BaseModel):
    config: CustomImageConfig
    state: CustomImageState


class LXCInstanceConfig(ResourceConfig):
    id: str
    appliance_id: str
    volume_id: str
    storage: str
    disk_size: int
    sector: str
    memory: int
    swap: int
    cores: int
    nfs: bool
    sector_name: str
    node: str
    
    @property
    def features(self) -> str:
        features = "nesting=1"
        if self.nfs:
            features += ",mount=nfs"
        return features


class LXCInstanceState(BaseModel):
    vmid: int = 0
    status: Annotated[data_types.ComputeStatus, data_types.SerializeEnum] = data_types.ComputeStatus.STARTING
    address: Annotated[IPv4Address, data_types.SerializeIP] | None = None


class LXCInstance(BaseModel):
    config: LXCInstanceConfig
    state: LXCInstanceState


class VMInstanceConfig(ResourceConfig):
    id: str
    cores: int
    sockets: int
    memory: int
    image_id: str
    volume_id: str
    storage: str
    disk_size: int
    sector: str
    user: str = "root"
    sector_name: str
    node: str

    @computed_field(repr=False)
    @property
    def vcpus(self) -> int:
        return self.cores * self.sockets


class VMInstanceState(BaseModel):
    vmid: int = 0
    status: Annotated[data_types.ComputeStatus, data_types.SerializeEnum] = data_types.ComputeStatus.STARTING
    address: Annotated[IPv4Address, data_types.SerializeIP] | None = None


class VMInstance(BaseModel):
    config: VMInstanceConfig
    state: VMInstanceState


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
    application_user: str
    application_database: str


class DataCoreNode(BaseModel):
    """Represents a DataCore cluster node with VM ID and name."""

    vmid: int
    name: str
    role: str = ""


class DataCoreNodes(RootModel[list[DataCoreNode]]):
    def get_node_by_vmid(self, vmid: int) -> DataCoreNode:
        return next(iter([node for node in self.root if node.vmid == vmid]))

    def get_node_by_name(self, name: str) -> DataCoreNode:
        return next(iter([node for node in self.root if node.name == name]))


class DataCoreState(BaseModel):
    nodes: DataCoreNodes = DataCoreNodes(root=[])
    status: Annotated[data_types.DataCoreStatus, data_types.SerializeEnum] = data_types.DataCoreStatus.PENDING


class DataCore(BaseModel):
    config: DataCoreConfig
    state: DataCoreState


class DockFSConfig(ResourceConfig):
    id: str
    name: str
    virtual_router_id: int = Field(ge=1, le=255)
    vip: Annotated[IPv4Interface, data_types.SerializeIP]
    memory_gb: int
    sockets: int
    cores: int
    capacity_gb: int
    storage: str
    
    @computed_field
    @property
    def vcpus(self) -> int:
        return self.sockets * self.cores


class DockFSNode(BaseModel):
    name: str
    address: Annotated[IPv4Interface, data_types.SerializeIP]
    vmid: int


class DockFSState(BaseModel):
    status: Annotated[data_types.DockFSStatus, data_types.SerializeEnum] = data_types.DockFSStatus.PENDING
    active: DockFSNode | None = None
    passive: DockFSNode | None = None

    @property
    def node_names(self) -> list[str]:
        return [node.name for node in (self.active, self.passive) if node]


class DockFS(BaseModel):
    config: DockFSConfig
    state: DockFSState


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


class HealthCheck(BaseModel):
    protocol: Annotated[data_types.HealthCheckProtocol, data_types.SerializeEnum] = data_types.HealthCheckProtocol.AGENT
    port: int = 80
    path: str = "/"
    timeout_seconds: int = 5
    success_count: int = 3
    failure_count: int = 2
    interval_seconds: int = 30
    warmup_seconds: int = 300


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
