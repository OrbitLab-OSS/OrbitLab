"""PKI Manifests."""

import hashlib
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Annotated, Literal, Self

from cryptography import x509
from pydantic import BaseModel, Field, model_validator

from orbitlab.data_types import KeyUsageTypes, ManifestKind, SSHKeyTypes
from orbitlab.manifest.ref import Ref
from orbitlab.manifest.secrets import SecretManifest
from orbitlab.services.pki.exceptions import CertificateFingerprintError

from .base import BaseManifest, Metadata, Spec
from .serialization import CertificateData, SerializeEnum, SerializeEnumList


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


class CertificateIssued(BaseModel):
    """Represents an issued certificate."""

    issuer: str
    not_before: datetime
    not_after: datetime
    certificate: CertificateData
    fingerprint: str
    serial_number: str
    secret: Ref

    @model_validator(mode="after")
    def check_fingerprint(self) -> Self:
        """Validate that the fingerprint matches the SHA-256 hash of the certificate."""
        certificate_hash = hashlib.sha256(self.certificate.encode()).hexdigest()
        if self.fingerprint != f"SHA256:{certificate_hash}":
            raise CertificateFingerprintError(serial_number=self.serial_number)
        return self


class CertificateIssuedWithChain(CertificateIssued):
    """Represents an issued certificate with its chain."""

    chain: CertificateData


class RootCertificateMetadata(Metadata):
    """Metadata for a root certificate authority."""

    name: str


class RootCertificateSpec(Spec):
    """Specification for a root certificate authority."""

    subject: Subject
    key_usage: Annotated[list[KeyUsageTypes], SerializeEnumList]
    issued: CertificateIssued | None = Field(default=None)


class RootCertificateManifest(BaseManifest[RootCertificateMetadata, RootCertificateSpec]):
    """Manifest class for root certificate authorities."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.ROOT_CERTIFICATE

    @property
    def status(self) -> Literal["valid", "warning", "expired", "not_issued"]:
        """Return the current status of the certificate based on its validity period."""
        if not self.spec.issued:
            return "not_issued"
        if self.spec.issued.not_after < datetime.now(UTC):
            return "expired"
        if self.spec.issued.not_after - timedelta(days=30) < datetime.now(UTC):
            return "warning"
        return "valid"

    @classmethod
    def create(cls, subject: Subject, key_usage: list[KeyUsageTypes]) -> Self:
        """Create a root certificate authority manifest."""
        manifest = cls(
            name=cls._generate_id("pki-rca"),
            metadata=RootCertificateMetadata(name=subject.common_name),
            spec=RootCertificateSpec(subject=subject, key_usage=key_usage),
        )
        manifest.save()
        return manifest

    def get_key(self) -> str:
        """Get the value of the PEM key from the vault."""
        if self.spec.issued:
            manifest = SecretManifest.from_ref(self.spec.issued.secret)
            return manifest.get_current_value()
        return ""

    def delete(self) -> None:
        """Delete the certificate key from the vault and remove the manifest."""
        if self.spec.issued:
            SecretManifest.from_ref(self.spec.issued.secret).delete()
        super().delete()


class IntermediateCertificateMetadata(Metadata):
    """Metadata for an intermediate certificate authority."""

    name: str
    domain_constraint: str


class IntermediateCertificateSpec(Spec):
    """Specification for an intermediate certificate authority."""

    subject: Subject
    root_ca: str
    issued: CertificateIssuedWithChain | None = Field(default=None)


class IntermediateCertificateManifest(BaseManifest[IntermediateCertificateMetadata, IntermediateCertificateSpec]):
    """Manifest class for intermediate certificate authorities."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.INTERMEDIATE_CERTIFICATE

    @property
    def status(self) -> Literal["valid", "warning", "expired", "not_issued"]:
        """Return the current status of the certificate based on its validity period."""
        if not self.spec.issued:
            return "not_issued"
        if self.spec.issued.not_after < datetime.now(UTC):
            return "expired"
        if self.spec.issued.not_after - timedelta(days=30) < datetime.now(UTC):
            return "warning"
        return "valid"

    @classmethod
    def create(cls, subject: Subject, root_ca: str, domain_constraint: str) -> Self:
        """Create a root certificate authority manifest."""
        manifest = cls(
            name=cls._generate_id("pki-ica"),
            metadata=IntermediateCertificateMetadata(
                name=subject.common_name,
                domain_constraint=domain_constraint,
            ),
            spec=IntermediateCertificateSpec(subject=subject, root_ca=root_ca),
        )
        manifest.save()
        return manifest

    def get_key(self) -> str:
        """Get the value of the PEM key from the vault."""
        if self.spec.issued:
            manifest = SecretManifest.from_ref(self.spec.issued.secret)
            return manifest.get_current_value()
        return ""

    def delete(self) -> None:
        """Delete the certificate key from the vault and remove the manifest."""
        if self.spec.issued:
            SecretManifest.from_ref(self.spec.issued.secret).delete()
        super().delete()


class LeafCertificateMetadata(Metadata):
    """Metadata for an intermediate certificate authority."""

    name: str
    san_dns: list[str]
    san_ips: list[str]


class LeafCertificateSpec(Spec):
    """Specification for an intermediate certificate authority."""

    subject: Subject
    server_auth: bool
    signing_ca: str
    issued: CertificateIssuedWithChain | None = Field(default=None)


class LeafCertificateManifest(BaseManifest[LeafCertificateMetadata, LeafCertificateSpec]):
    """Manifest class for intermediate certificate authorities."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.LEAF_CERTIFICATE

    @property
    def status(self) -> Literal["valid", "warning", "expired", "not_issued"]:
        """Return the current status of the certificate based on its validity period."""
        if not self.spec.issued:
            return "not_issued"
        if self.spec.issued.not_after < datetime.now(UTC):
            return "expired"
        if self.spec.issued.not_after - timedelta(days=30) < datetime.now(UTC):
            return "warning"
        return "valid"

    def get_x509_san(self) -> x509.SubjectAlternativeName | None:
        """Returns an x509.SubjectAlternativeName object if SANs are present, otherwise returns None."""
        general_names = []
        if self.metadata.san_dns:
            general_names.extend([x509.DNSName(value=name) for name in self.metadata.san_dns])
        if self.metadata.san_ips:
            general_names.extend(
                [x509.IPAddress(value=ip_address(address=address)) for address in self.metadata.san_ips],
            )
        if general_names:
            return x509.SubjectAlternativeName(general_names=general_names)
        return None

    @classmethod
    def create(
        cls, subject: Subject, san_dns: list[str], san_ips: list[str], signing_ca: str, *, server_auth: bool,
    ) -> Self:
        """Create a root certificate authority manifest."""
        manifest = cls(
            name=cls._generate_id("pki-leaf"),
            metadata=LeafCertificateMetadata(
                name=subject.common_name,
                san_dns=san_dns,
                san_ips=san_ips,
            ),
            spec=LeafCertificateSpec(subject=subject, signing_ca=signing_ca, server_auth=server_auth),
        )
        manifest.save()
        return manifest

    def get_key(self) -> str:
        """Get the value of the PEM key from the vault."""
        if self.spec.issued:
            manifest = SecretManifest.from_ref(self.spec.issued.secret)
            return manifest.get_current_value()
        return ""

    def delete(self) -> None:
        """Delete the certificate key from the vault and remove the manifest."""
        if self.spec.issued:
            SecretManifest.from_ref(self.spec.issued.secret).delete()
        super().delete()


class SSHKeyMetadata(Metadata):
    """Metadata for an SSH kek."""

    key_type: Annotated[SSHKeyTypes, SerializeEnum]
    passphrase: bool


class SSHKeySpec(Spec):
    """Specification for an SSH Key."""

    public_key: str
    fingerprint: str
    private_key: Ref


class SSHKeyManifest(BaseManifest[SSHKeyMetadata, SSHKeySpec]):
    """Manifest class for storing SSH key metadata and specification."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.SSH_KEY

    def get_private_key(self) -> str:
        """Get the value of the private key from the vault."""
        manifest = SecretManifest.from_ref(self.spec.private_key)
        return manifest.get_current_value()
