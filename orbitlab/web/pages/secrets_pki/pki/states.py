"""OrbitLab PKI Page states."""

from typing import Literal

import reflex as rx

from orbitlab.data_types import CertificateTypes, ManifestKind
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.secrets import CertificateManifest


class LoadCertificates:
    """Utility class for loading certificates from the manifest client."""

    @classmethod
    def __load__(cls, cert_type: CertificateTypes) -> list[CertificateManifest]:
        """Load and return certificates of the specified type."""
        client = ManifestClient()
        certs = list(client.get_existing_by_kind(kind=ManifestKind.CERTIFICATE).keys())
        certificate_authorities = []
        for cert in certs:
            manifest: CertificateManifest = client.load(cert, kind=ManifestKind.CERTIFICATE)
            if manifest.metadata.type == cert_type:
                certificate_authorities.append(manifest)
        return certificate_authorities

    @classmethod
    def intermediate(cls) -> list[CertificateManifest]:
        """Load and return all intermediate certificate manifests."""
        return cls.__load__(CertificateTypes.INTERMEDIATE)

    @classmethod
    def certificate_authorities(cls) -> list[CertificateManifest]:
        """Load and return all root certificate authority manifests."""
        return cls.__load__(CertificateTypes.ROOT)


class CAState(rx.State):
    """State for managing Certificate Authorities."""

    certificate_authorities: list[CertificateManifest] = rx.field(
        default_factory=LoadCertificates.certificate_authorities,
    )
    ca_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var
    def certificate_authority_names(self) -> list[str]:
        """Get a list of certificate authority names."""
        return [cert.name for cert in self.certificate_authorities]

    @rx.var
    def filtered_cas(self) -> list[CertificateManifest]:
        """Filter certificate authorities based on the current filter setting."""
        if self.ca_filter == "All":
            return self.certificate_authorities
        return [ca for ca in self.certificate_authorities if ca.metadata.status == self.ca_filter.lower()]


class IntermediateCAState(rx.State):
    """State for managing Certificate Authorities."""

    intermediate_certificates: list[CertificateManifest] = rx.field(default_factory=LoadCertificates.intermediate)
    root_certificates: list[str] = rx.field(default_factory=LoadCertificates.certificate_authorities)
    cert_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var
    def filtered_certificates(self) -> list[CertificateManifest]:
        """Filter intermediate certificates based on the current filter setting."""
        if self.cert_filter == "All":
            return self.intermediate_certificates
        return [ca for ca in self.intermediate_certificates if ca.metadata.status == self.cert_filter.lower()]


class ManageCA(rx.State):
    """State for managing individual Certificate Authority operations."""

    manifest: CertificateManifest | None = None
    revoke_disabled: bool = True

    @rx.var
    def download_name(self) -> str:
        """Generate a download-friendly filename from the manifest name."""
        if self.manifest:
            return self.manifest.name.replace(" ", "_").lower()
        return ""


class ManageIntermediateCerts(rx.State):
    """State for managing intermediate certificates."""

    manifest: CertificateManifest | None = None
    revoke_disabled: bool = True
