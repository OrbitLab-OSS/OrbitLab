"""Data types and enumerations for OrbitLab."""

from enum import StrEnum, auto
from types import FunctionType

from reflex.event import EventCallback, EventHandler, EventSpec

type FrontendEvents = (
    EventCallback | EventHandler | EventSpec | list[EventCallback | EventHandler | EventSpec] | FunctionType
)


class ManifestKind(StrEnum):
    """Enumeration of possible manifest kinds in OrbitLab."""

    BASE_APPLIANCE = auto()
    CUSTOM_APPLIANCE = auto()
    CLUSTER = auto()
    NODE = auto()
    IPAM = auto()
    SECTOR = auto()
    LXC = auto()
    SECRET = auto()
    CERTIFICATE = auto()
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


class CertificateTypes(StrEnum):
    """Enumeration of possible certificate types in OrbitLab."""

    ROOT = auto()
    INTERMEDIATE = auto()
    LEAF = auto()
    CLIENT = auto()


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
    LINSTOR = auto()


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


class OrbitLabApplianceType(StrEnum):
    """Enumeration of possible OrbitLab appliance types."""

    SECTOR_GATEWAY = "SectorGateway"
    SECTOR_DNS = "SectorDNS"
    BACKPLANE_DNS = "BackplaneDNS"


class TaskStatus(StrEnum):
    """Enumeration of possible appliance types in OrbitLab."""

    RUNNING = auto()
    STOPPED = auto()


class CustomApplianceStepType(StrEnum):
    """Enumeration of possible custom appliance step types in OrbitLab."""

    SCRIPT = auto()
    FILES = auto()


class ClusterMode(StrEnum):
    """Enumeration of possible cluster modes in OrbitLab."""

    LOCAL = auto()
    CLUSTER = auto()


class InitializationState(StrEnum):
    """Enumeration of possible initialization states in OrbitLab."""

    NOT_STARTED = auto()
    RUNNING = auto()
    BACKPLANE = auto()
    FINALIZE = auto()
    ABORTED = auto()
    COMPLETE = auto()


class SectorState(StrEnum):
    """Enumeration of possible sector states in OrbitLab."""

    PENDING = auto()
    AVAILABLE = auto()
    DELETING = auto()


class CustomApplianceWorkflowStatus(StrEnum):
    """Enumeration of possible workflow statuses for custom appliances in OrbitLab."""

    PENDING = auto()
    STARTING = auto()
    RUNNING = auto()
    FINALIZING = auto()
    SUCCEEDED = auto()
    FAILED = auto()


class LXCState(StrEnum):
    """Enumeration of possible LXC States in OrbitLab."""

    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    RESTARTING = auto()
    TERMINATING = auto()


class LXCStatus(StrEnum):
    """Enumeration of possible LXC Status requests for Proxmox."""

    REBOOT = auto()
    START = auto()
    STOP = auto()
    SHUTDOWN = auto()


class HealthCheckProtocol(StrEnum):
    """Enumeration of possible Health Check Protocols in OrbitLab."""

    HTTP = auto()
    HTTPS = auto()
