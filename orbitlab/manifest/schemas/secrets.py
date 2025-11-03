"""Schemas for secret, certificate, and SSH key manifests.

This module defines Pydantic models for secrets, certificates, and SSH keys,
including their metadata and specifications.
"""  # noqa: A005
import hashlib
from datetime import datetime
from typing import Annotated, Self

from pydantic import Field, model_validator

from orbitlab.data_types import CertificateTypes, CSRStatus, KeyUsageTypes, ManifestKind, SSHKeyTypes
from orbitlab.services.pki.exceptions import CertificateFingerprintError

from .base import BaseManifest, Metadata, Spec
from .serialization import SerializeEnum, SerializeEnumList


class SecretSpec(Spec):
    """Specification for a secret.

    Args:
        secret_name (str): The name of the secret. Must match the specified pattern.
        version (int): The current version of the secret. Must be greater than or equal to 1.
        previous_versions (set[int]): A set of previous version numbers for the secret.
    """
    secret_name: Annotated[str, Field(pattern="^/?(?:[A-Za-z0-9]+(?:/[A-Za-z0-9]+)*)?/?$")]
    version: Annotated[int, Field(ge=1)]
    previous_versions: Annotated[list[int], Field(default_factory=list)]


class SecretMetadata(Metadata):
    """Metadata for a secret, including an optional description."""
    description: Annotated[str | None, Field(default=None)]


class SecretManifest(BaseManifest[SecretMetadata, SecretSpec]):
    """Manifest class for storing secret metadata and specification."""
    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.SECRET


class CertificateMetadata(Metadata):
    """Metadata for a certificate, including type, subject, issuer, validity, and other details.

    Attributes:
        type (CertificateTypes): The type of certificate.
        common_name (str): The common name (CN) of the certificate subject.
        issuer (str): The issuer of the certificate.
        not_before (datetime): The start of the certificate's validity period.
        not_after (datetime): The end of the certificate's validity period.
        algorithm (str): The algorithm used for the certificate.
        certificate (str): The certificate data in PEM format.
        fingerprint (str): The fingerprint of the certificate.
        path_length (int | None): The path length constraint for CA certificates.
        san_dns (list[str]): Subject Alternative Name DNS entries.
        san_ips (list[str]): Subject Alternative Name IP entries.
        key_usage (list[str]): Key usage extensions.
        serial_number (int): The serial number of the certificate.
    """
    type: Annotated[CertificateTypes, SerializeEnum]
    common_name: str
    issuer: str
    org: str
    org_unit: str
    country: str
    state_or_province: str
    locality: str
    not_before: datetime
    not_after: datetime
    certificate: str
    fingerprint: str
    key_usage: Annotated[list[KeyUsageTypes], SerializeEnumList]
    serial_number: int

    # Intermediate CAs
    domain_constraint: Annotated[str | None, Field(default=None)]

    # Leaf Certificates
    san_dns: Annotated[list[str] | None, Field(default=None)]
    san_ips: Annotated[list[str] | None, Field(default=None)]
    chain: Annotated[str | None, Field(default=None)]

    @model_validator(mode="after")
    def check_fingerprint(self) -> Self:
        """Validate that the fingerprint matches the SHA-256 hash of the certificate.

        Raises:
            CertificateFingerprintError: If the fingerprint does not match the calculated hash.
        """
        if self.fingerprint != f"SHA256:{hashlib.sha256(self.certificate.encode()).hexdigest()}":
            raise CertificateFingerprintError(common_name=self.common_name, serial_number=self.serial_number)
        return self


class CertificateManifest(BaseManifest[CertificateMetadata, SecretSpec]):
    """Manifest class for storing certificate metadata and specification."""
    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.CERTIFICATE


class CSRMetadata(Metadata):
    """Metadata for a Certificate Signing Request (CSR), including subject details, key usage, and issuance information.

    Attributes:
        type (CertificateTypes): The type of certificate requested.
        common_name (str): The common name (CN) of the certificate subject.
        issuer (str): The issuer of the certificate.
        org (str): The organization of the certificate subject.
        org_unit (str): The organizational unit of the certificate subject.
        country (str): The country of the certificate subject.
        state_or_province (str): The state or province of the certificate subject.
        locality (str): The locality of the certificate subject.
        key_usage (list[KeyUsageTypes]): Key usage extensions requested.
        san_dns (list[str] | None): Subject Alternative Name DNS entries.
        san_ips (list[str] | None): Subject Alternative Name IP entries.
        serial_number (int | None): Serial number after issuance.
        not_before (datetime | None): Validity start after issuance.
        not_after (datetime | None): Validity end after issuance.
        certificate (str | None): Certificate data after issuance.
        chain (str | None): Certificate chain after issuance.
        fingerprint (str | None): Certificate fingerprint after issuance.
    """
    type: Annotated[CertificateTypes, SerializeEnum] = CertificateTypes.LEAF
    common_name: str
    issuer: str
    org: str
    org_unit: str
    country: str
    state_or_province: str
    locality: str
    key_usage: Annotated[list[KeyUsageTypes], SerializeEnumList]
    san_dns: Annotated[list[str] | None, Field(default=None)]
    san_ips: Annotated[list[str] | None, Field(default=None)]

    # After issuance
    serial_number: Annotated[int | None, Field(default=None)]
    not_before: Annotated[datetime | None, Field(default=None)]
    not_after: Annotated[datetime | None, Field(default=None)]
    certificate: Annotated[str | None, Field(default=None)]
    chain: Annotated[str | None, Field(default=None)]
    fingerprint: Annotated[str | None, Field(default=None)]


class CSRSpec(Spec):
    """Specification for a Certificate Signing Request (CSR).

    Attributes:
        key_fingerprint (str): The fingerprint of the key associated with the CSR.
        csr_fingerprint (str): The fingerprint of the CSR.
        submitted_at (datetime): The datetime when the CSR was submitted.
        signed_at (datetime | None): The datetime when the CSR was signed, if applicable.
        status (CSRStatus): The current status of the CSR.
    """
    key_fingerprint: str
    csr_fingerprint: str
    submitted_at: datetime
    signed_at: Annotated[datetime | None, Field(default=None)]
    rejected_at: Annotated[datetime | None, Field(default=None)]
    status: Annotated[CSRStatus, SerializeEnum]
    rejected_reason: Annotated[str | None, Field(default=None)]


class CSRManifest(BaseManifest[CSRMetadata, CSRSpec]):
    """Manifest class for storing Certificate Signing Request (CSR) metadata and specification."""
    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.CSR


class SSHKeyMetadata(Metadata):
    """Metadata for an SSH key, including public key, fingerprint, type, and passphrase status.

    Attributes:
        public_key (str): The SSH public key.
        fingerprint (str): The fingerprint of the SSH key.
        key_type (SSHKeyTypes): The type of SSH key.
        passphrase (bool): Indicates if the key is protected by a passphrase.
    """
    public_key: str
    fingerprint: str
    key_type: Annotated[SSHKeyTypes, SerializeEnum]
    passphrase: bool


class SSHKeyManifest(BaseManifest[SSHKeyMetadata, SecretSpec]):
    """Manifest class for storing SSH key metadata and specification."""
    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.SSH_KEY
