"""
Constants for OrbitLab.

This module defines file system paths and other immutable values used throughout the application.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Final

ORBITLAB_ROOT: Final = Path("./TEST_ROOT")  # TODO: Change to "/etc/pve/orbitlab"
MANIFEST_ROOT: Final = ORBITLAB_ROOT / "manifests"
WORKFLOW_FILES_ROOT: Final = ORBITLAB_ROOT / "workflow-files"

DNS_ROOT: Final = ORBITLAB_ROOT / "dns"
DNS_ZONE_ROOT: Final = DNS_ROOT / "zones"

SECRETS_ROOT: Final = ORBITLAB_ROOT / "secrets"
PKI_ROOT: Final = SECRETS_ROOT / "pki"


class PKI(SimpleNamespace):
    """Constants related to Public Key Infrastructure (PKI) settings.

    Attributes:
        RSA_PUBLIC_EXPONENT (int): The public exponent value for RSA keys.
        RSA_KEY_SIZE (int): The key size for RSA keys in bits.
        ROOT_CA_DAYS_VALID (int): Number of days the root CA certificate is valid.
        INTERMEDIATE_CA_DAYS_VALID (int): Number of days the intermediate CA certificate is valid.
        LEAF_CA_DAYS_VALID (int): Number of days the leaf CA certificate is valid.
    """

    RSA_PUBLIC_EXPONENT: Final = 65537
    RSA_KEY_SIZE: Final = 4096

    ROOT_CA_DAYS_VALID: Final = 20 * 365  # 356 days a year for 20 years
    INTERMEDIATE_CA_DAYS_VALID: Final = 5 * 365  # 356 days a year for 5 years
    LEAF_CA_DAYS_VALID: Final = 365  # 1 year
