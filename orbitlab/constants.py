"""Constants for OrbitLab."""

from types import SimpleNamespace
from typing import Final, LiteralString


class PKI(SimpleNamespace):
    """Constants related to Public Key Infrastructure (PKI) settings."""

    RSA_PUBLIC_EXPONENT: Final = 65537
    RSA_KEY_SIZE: Final = 4096

    ROOT_CA_DAYS_VALID: Final = 20 * 365  # 356 days a year for 20 years
    INTERMEDIATE_CA_DAYS_VALID: Final = 5 * 365  # 356 days a year for 5 years
    LEAF_CA_DAYS_VALID: Final = 365  # 1 year


class Backplane(SimpleNamespace):
    """Constants for the OrbitLab backplane network configuration."""

    NAME: Final = "bckplane"
    ALIAS: Final = "OrbitLab Backplane"
    ASN: Final = 65001
    ZONE_TAG: Final = 10
    VNET_TAG: Final = 100
    DEFAULT_CIDR: Final = "100.96.0.0/16"
    DEFAULT_GATEWAY: Final = "100.96.0.1"
    NETWORK_REGEX_PATTERN: Final = (
        r"^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\/(?:[89]|1\d|2[0-4])$"
    )


class NetworkSettings(SimpleNamespace):
    """Constants for OrbitLab's networking settings."""

    BACKPLANE = Backplane
    RESERVED_INFRA_IPS: Final = 10
    RESERVED_BROADCAST_IPS: Final = -5
    RESERVED_SECTOR_IPS = 50


SCRIPT = """cat <<'EOF' > {filename}
#!/bin/bash
set -euo pipefail
{content}
rm -f {filename}
EOF
"""


class ProxmoxRE(SimpleNamespace):
    """Constants for Proxmox-related remote execution operations."""

    SCRIPT: LiteralString = SCRIPT
    USER = "orbitlab@pve"


class EventStreams(SimpleNamespace):
    """Constants for OrbitLab event stream identifiers."""

    WORKFLOWS = "ol:workflows"
    EVENTS = "ol:events"
    WORKFLOW_LOGS = "ol:logs:workflows"
    SYSTEM_LOGS = "ol:logs:system"
