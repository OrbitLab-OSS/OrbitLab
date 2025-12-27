"""Constants for OrbitLab."""

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Final, LiteralString


class Directories(SimpleNamespace):
    """Directory paths for OrbitLab file system structure."""

    ORBITLAB_ROOT: Final = Path().cwd() / "TEST_ROOT" if \
        bool(os.environ.get("ORBITLAB_DEV")) else Path("/etc/pve/orbitlab")
    MANIFEST_ROOT: Final = ORBITLAB_ROOT / "manifests"
    WORKFLOW_FILES_ROOT: Final = ORBITLAB_ROOT / "workflow-files"

    CUSTOM_APPLIANCES: Final = WORKFLOW_FILES_ROOT / "custom_appliances"

    DNS_ROOT: Final = ORBITLAB_ROOT / "dns"
    DNS_ZONE_ROOT: Final = DNS_ROOT / "zones"

    SECRETS_ROOT: Final = ORBITLAB_ROOT / "secrets"
    VAULT: Final = SECRETS_ROOT / "vault"
    PKI_ROOT: Final = SECRETS_ROOT / "pki"

    def make_dirs(self) -> None:
        """Create all directories defined in this class."""
        for attr in self.__annotations__:
            directory: Path = getattr(self, attr)
            directory.mkdir(parents=True, exist_ok=True)

Directories().make_dirs()


class PKI(SimpleNamespace):
    """Constants related to Public Key Infrastructure (PKI) settings."""

    RSA_PUBLIC_EXPONENT: Final = 65537
    RSA_KEY_SIZE: Final = 4096

    ROOT_CA_DAYS_VALID: Final = 20 * 365  # 356 days a year for 20 years
    INTERMEDIATE_CA_DAYS_VALID: Final = 5 * 365  # 356 days a year for 5 years
    LEAF_CA_DAYS_VALID: Final = 365  # 1 year

class Backplane(SimpleNamespace):
    """Constants for the OrbitLab backplane network configuration."""

    IPAM: Final = "backplane"
    NAME: Final = "bckplane"
    ALIAS: Final = "OrbitLab Backplane"
    ASN: Final = 65001
    ZONE_TAG: Final = 10
    VNET_TAG: Final = 100
    DEFAULT_CIDR: Final = "10.200.0.0/16"
    DEFAULT_GATEWAY: Final = "10.200.0.1"
    NETWORK_REGEX_PATTERN: Final = (
        r"^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\/(?:[89]|1\d|2[0-4])$"
    )


class NetworkSettings(SimpleNamespace):
    """Constants for OrbitLab's networking settings."""

    BACKPLANE = Backplane
    RESERVED_USABLE_IPS: Final = 10


SCRIPT = """cat <<EOF > {filename}
#!/bin/bash
set -euo pipefail
{content}
EOF
"""


class ProxmoxRE(SimpleNamespace):
    """Constants for Proxmox-related remote execution operations."""

    SCRIPT: LiteralString = SCRIPT
