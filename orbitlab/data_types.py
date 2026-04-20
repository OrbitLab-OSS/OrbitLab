"""Data types and enumerations for OrbitLab."""

from enum import StrEnum, auto
from types import FunctionType
from typing import Literal

from reflex.event import EventCallback, EventHandler, EventSpec

import base64
import binascii
from collections.abc import Callable
from enum import StrEnum
from ipaddress import IPv4Address
from typing import Annotated, TypeVar

from pydantic import PlainSerializer, PlainValidator


T = TypeVar("T", bound=StrEnum)


def _str_list_to_enum(enum: T) -> Callable[[T], list[T]]:
    """Convert a list of strings to the specified Enums."""

    def wrapped(string_list: str | list) -> list[T]:
        if not isinstance(string_list, list):
            string_list = string_list.split(",")
        return [enum(i) for i in string_list]  # pyright: ignore[reportCallIssue]

    return wrapped


def _peer_list_str(peer_list: str) -> list[IPv4Address]:
    """Convert a comma-separated string of IP addresses to a list of IPv4Address objects."""
    return [IPv4Address(addr) for addr in peer_list.split(sep=",")]


def _serialize_enum_list(enums: list[StrEnum]) -> list[str]:
    """Serialize a list of Enums to list of strings."""
    return [enum.value for enum in enums]


def _base64_to_str(data: str) -> str:
    """Decode a base64-encoded string to its original string value."""
    try:
        return base64.b64decode(data, validate=True).decode()
    except binascii.Error:
        return data


def _to_base64(data: str) -> str:
    """Encode a string to base64."""
    return base64.b64encode(data.encode()).decode()


SerializeEnum = PlainSerializer(lambda v: v.value)
SerializeEnumList = PlainSerializer(_serialize_enum_list)
SerializePath = PlainSerializer(lambda v: str(v))
SerializeIP = PlainSerializer(lambda addr: str(addr))
SerializeIPList = PlainSerializer(lambda addrs: [str(addr) for addr in addrs])


class ManifestKind(StrEnum):
    """Enumeration of possible manifest kinds in OrbitLab."""

    BASE_APPLIANCE = auto()
    CUSTOM_APPLIANCE = auto()
    BASE_IMAGE = auto()
    CUSTOM_IMAGE = auto()
    CLUSTER = auto()
    DOCK_FS = auto()
    DATA_CORE = auto()
    NODE = auto()
    SECTOR = auto()
    DNS = auto()
    LXC = auto()
    VM = auto()
    SECRET = auto()
    ROOT_CERTIFICATE = auto()
    INTERMEDIATE_CERTIFICATE = auto()
    LEAF_CERTIFICATE = auto()
    CSR = auto()
    SSH_KEY = auto()
    AUTOSCALING = auto()


class NodeStatus(StrEnum):
    """Enumeration of possible node statuses in OrbitLab."""

    ONLINE = auto()
    OFFLINE = auto()
    UNKNOWN = auto()


class NetworkTypes(StrEnum):
    """Enumeration of possible network types in OrbitLab."""

    BRIDGE = auto()
    BOND = auto()
    ETH = auto()
    ALIAS = auto()
    VLAN = auto()
    FABRIC = auto()
    VNET = auto()
    UNKNOWN = auto()
    OVS_BRIDGE = "OVSBridge"
    OVS_BOND = "OVSBond"
    OVS_PORT = "OVSPort"
    OVS_INT_PORT = "OVSIntPort"


class ZoneTypes(StrEnum):
    """Enumeration of possible SDN zone types in OrbitLab."""

    EVPN = auto()
    FAUCET = auto()
    QINQ = auto()
    SIMPLE = auto()
    VLAN = auto()
    VXLAN = auto()


class NetworkMethods(StrEnum):
    """Enumeration of possible network methods in OrbitLab."""

    LOOPBACK = auto()
    DHCP = auto()
    MANUAL = auto()
    STATIC = auto()
    AUTO = auto()


class SSHKeyTypes(StrEnum):
    """Enumeration of possible SSH key types in OrbitLab."""

    RSA = auto()
    ED25519 = auto()


class KeyUsageTypes(StrEnum):
    """Enumeration of possible key usage types in OrbitLab."""

    DIGITAL_SIGNATURE = auto()
    KEY_ENCIPHERMENT = auto()
    KEY_CERT_SIGN = auto()
    DATA_ENCIPHERMENT = auto()
    CRL_SIGN = auto()
    CONTENT_COMMITMENT = auto()
    KEY_AGREEMENT = auto()
    ENCIPHER_ONLY = auto()
    DECIPHER_ONLY = auto()

    @classmethod
    def to_x509_usage_params(cls, key_usages: list["KeyUsageTypes"]) -> dict[str, bool]:
        """Convert a list of KeyUsageTypes to x509 usage parameter dictionary.

        Parameters:
            key_usages (list[KeyUsageTypes]): List of key usage types to be converted.

        Returns:
            dict[str, bool]: Dictionary mapping x509 usage parameter names to boolean values.
        """
        return {str(usage): usage in key_usages for usage in cls}


class CSRStatus(StrEnum):
    """Enumeration of possible CSR (Certificate Signing Request) statuses in OrbitLab."""

    PENDING = auto()
    ISSUED = auto()
    REJECTED = auto()


class StorageContentType(StrEnum):
    """Enumeration of possible storage content types in OrbitLab."""

    BACKUP = auto()
    IMAGES = auto()
    ROOTDIR = auto()
    SNIPPETS = auto()
    VZTMPL = auto()
    ISO = auto()
    IMPORT = auto()


class StorageProfile(StrEnum):
    """Enumeration of possible storage profiles in OrbitLab."""

    LOCAL = auto()
    # LINSTOR = auto()


class StorageType(StrEnum):
    """Enumeration of possible storage types in OrbitLab."""

    BTRFS = auto()
    CEPHFS = auto()
    CIFS = auto()
    DIR = auto()
    ESXI = auto()
    ISCSI = auto()
    ISCSIDIRECT = auto()
    LVM = auto()
    LVMTHIN = auto()
    NFS = auto()
    PBS = auto()
    RBD = auto()
    ZFS = auto()
    ZFSPOOL = auto()


class ApplianceType(StrEnum):
    """Enumeration of possible appliance types in OrbitLab."""

    SYSTEM = auto()
    TURNKEY = auto()


class TaskStatus(StrEnum):
    """Enumeration of possible appliance types in OrbitLab."""

    RUNNING = auto()
    STOPPED = auto()


class WorkflowStepType(StrEnum):
    """Enumeration of possible custom appliance step types in OrbitLab."""

    SCRIPT = auto()
    FILES = auto()


class ClusterMode(StrEnum):
    """Enumeration of possible cluster modes in OrbitLab."""

    LOCAL = auto()
    CLUSTER = auto()


class InitializationStatus(StrEnum):
    """Enumeration of possible initialization states in OrbitLab."""

    UNKNOWN = auto()
    NOT_STARTED = auto()
    RUNNING = auto()
    ABORTED = auto()
    COMPLETE = auto()


class SectorStatus(StrEnum):
    """Enumeration of possible sector states in OrbitLab."""

    PENDING = auto()
    AVAILABLE = auto()
    DELETING = auto()


class TemplateWorkflowStatus(StrEnum):
    """Enumeration of possible workflow statuses for custom appliances in OrbitLab."""

    NEVER_RAN = auto()
    PENDING = auto()
    STARTING = auto()
    RUNNING = auto()
    FINALIZING = auto()
    SUCCEEDED = auto()
    FAILED = auto()


class ComputeStatus(StrEnum):
    """Enumeration of possible Compute States in OrbitLab."""

    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    RESTARTING = auto()
    TERMINATING = auto()


class ProxmoxComputeStatus(StrEnum):
    """Enumeration of possible Compute Status requests for Proxmox."""

    REBOOT = auto()
    START = auto()
    STOP = auto()
    SHUTDOWN = auto()
    TERMINATE = auto()

    @classmethod
    def get_state(cls, status: str | StrEnum) -> ComputeStatus:
        """Return the ComputeState corresponding to the given ComputeStatus."""
        if isinstance(status, StrEnum):
            status = status.value
        match status:
            case "reboot":
                return ComputeStatus.RESTARTING
            case "start":
                return ComputeStatus.STARTING
            case "stop":
                return ComputeStatus.STOPPING
            case "shutdown":
                return ComputeStatus.STOPPING
            case "terminate":
                return ComputeStatus.TERMINATING
        raise ValueError


class HealthCheckProtocol(StrEnum):
    """Enumeration of possible Health Check Protocols in OrbitLab."""

    AGENT = auto()
    HTTP = auto()


class EventStatus(StrEnum):
    IN_PROGRESS = "in-progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WorkflowStatus(StrEnum):
    PENDING = auto()
    VALIDATING = auto()
    PROVISIONING = auto()
    CONFIGURING = auto()
    FINALIZING = auto()
    SUCCEEDED = auto()
    FAILED = auto()


class ETCDStatus(StrEnum):
    ABSENT = auto()
    PENDING = auto()
    DEGRADED = auto()
    AVAILABLE = auto()
    UPGRADING = auto()
    DELETING = auto()


class DockFSStatus(StrEnum):
    PENDING = auto()
    DEGRADED = auto()
    AVAILABLE = auto()
    DELETING = auto()


class DataCoreStatus(StrEnum):
    PENDING = auto()
    DEGRADED = auto()
    AVAILABLE = auto()
    DELETING = auto()


class DataCoreEvent(StrEnum):
    ON_START = "on_start"
    ON_STOP = "on_stop"
    ON_ROLE_CHANGE = "on_role_change"


class DataCoreNodeRole(StrEnum):
    PRIMARY = auto()
    REPLICA = auto()


type PveBool = Annotated[bool, PlainValidator(lambda v: v if isinstance(v, bool) else bool(v))]
type PveContentList = Annotated[
    list[StorageContentType],
    PlainValidator(func=_str_list_to_enum(enum=StorageContentType)),
    SerializeEnumList,
]
type PeerList = Annotated[list[IPv4Address], PlainValidator(func=_peer_list_str), SerializeIPList]
type PveStorageType = Annotated[StorageType, SerializeEnum]
type CertificateData = Annotated[str, PlainValidator(_base64_to_str), PlainSerializer(_to_base64)]
type FrontendEvents = (
    EventCallback | EventHandler | EventSpec | list[EventCallback | EventHandler | EventSpec] | FunctionType
)
type StreamEventData = tuple[bytes, dict[bytes, bytes]]
type RedisStreamEvent = tuple[bytes, tuple[StreamEventData]]
type EventReturn = EventHandler | EventSpec | list[EventHandler | EventSpec]
type OrbitLabApplianceType = Literal["backplane-dns", "gateway", "datacore", "dockfs", "etcd", "relay"]
type ZoneType = Literal["internal", "external"]
