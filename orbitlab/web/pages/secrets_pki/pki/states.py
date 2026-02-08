"""OrbitLab PKI Page states."""

from datetime import UTC, datetime
from typing import Literal

import reflex as rx

from orbitlab.data_types import CertificateTypes, KeyUsageTypes
from orbitlab.manifest.secrets import CertificateManifest
from orbitlab.web.utilities import CacheBuster


class CertificatesState(CacheBuster, rx.State):
    """State for managing and retrieving certificate manifests."""

    @rx.var(deps=["_cached_certificates"])
    def certificates(self) -> list[CertificateManifest]:
        """Get all existing certificate manifests."""
        return [CertificateManifest.load(name=name) for name in CertificateManifest.get_existing()]

    @rx.var
    def certificate_authorities(self) -> list[CertificateManifest]:
        """Get all root certificate authority manifests from the certificates list."""
        return [cert for cert in self.certificates if cert.metadata.type == CertificateTypes.ROOT]

    @rx.var
    def intermediate_certificates(self) -> list[CertificateManifest]:
        """Get all intermediate certificate authority manifests from the certificates list."""
        return [cert for cert in self.certificates if cert.metadata.type == CertificateTypes.INTERMEDIATE]

    @rx.var
    def leaf_certificates(self) -> list[CertificateManifest]:
        """Get all leaf certificate manifests from the certificates list."""
        return [cert for cert in self.certificates if cert.metadata.type == CertificateTypes.LEAF]


class CertificateAuthoritiesState(CertificatesState):
    """State for managing Certificate Authorities."""

    cert_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var
    def names(self) -> list[str]:
        """Get a list of certificate authority names."""
        return [cert.name for cert in self.certificate_authorities]

    @rx.var
    def filtered_certificates(self) -> list[CertificateManifest]:
        """Filter certificate authorities based on the current filter setting."""
        if self.cert_filter == "All":
            return self.certificate_authorities
        return [ca for ca in self.certificate_authorities if ca.metadata.status == self.cert_filter.lower()]


class IntermediateCertificatesState(CertificatesState):
    """State for managing Intermediate Certificate Authorities."""

    cert_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var
    def names(self) -> list[str]:
        """Get a list of intermediate certificate authority names."""
        return [cert.name for cert in self.intermediate_certificates]

    @rx.var
    def filtered_certificates(self) -> list[CertificateManifest]:
        """Filter intermediate certificates based on the current filter setting."""
        if self.cert_filter == "All":
            return self.intermediate_certificates
        return [ca for ca in self.intermediate_certificates if ca.metadata.status == self.cert_filter.lower()]


class LeafCertificatesState(CertificatesState):
    """State for managing Leaf Certificates."""

    cert_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var
    def names(self) -> list[str]:
        """Get a list of intermediate certificate authority names."""
        return [cert.name for cert in self.leaf_certificates]

    @rx.var
    def filtered_certificates(self) -> list[CertificateManifest]:
        """Filter intermediate certificates based on the current filter setting."""
        if self.cert_filter == "All":
            return self.leaf_certificates
        return [ca for ca in self.leaf_certificates if ca.metadata.status == self.cert_filter.lower()]


class ManageCertificateState(rx.State):
    """State for managing individual Certificate Authority operations."""

    _manifest: CertificateManifest | None = None
    revoke_disabled: bool = True
    delete_disabled: bool = True

    @rx.var
    def name(self) -> str:
        """Get the name of the current certificate manifest, or an empty string if not set."""
        if self._manifest:
            return self._manifest.name
        return ""

    @rx.var
    def common_name(self) -> str:
        """Get the common name of the current certificate manifest, or an empty string if not set."""
        if self._manifest:
            return self._manifest.metadata.common_name
        return ""

    @rx.var
    def issuer(self) -> str:
        """Get the issuer of the current certificate manifest, or an empty string if not set."""
        if self._manifest:
            if self._manifest.metadata.common_name == self._manifest.metadata.issuer:
                return "Self"
            return self._manifest.metadata.issuer
        return ""

    @rx.var
    def serial_number(self) -> str:
        """Get the serial number of the current certificate manifest, or an empty string if not set."""
        if self._manifest:
            return self._manifest.metadata.serial_number
        return ""

    @rx.var
    def org(self) -> str:
        """Get the organization of the current certificate manifest, or an empty string if not set."""
        if self._manifest:
            return self._manifest.metadata.org
        return ""

    @rx.var
    def org_unit(self) -> str:
        """Get the organizational unit of the current certificate manifest, or an empty string if not set."""
        if self._manifest:
            return self._manifest.metadata.org_unit
        return ""

    @rx.var
    def country(self) -> str:
        """Get the counter of the current certificate manifest, or an empty string if not set."""
        if self._manifest:
            return self._manifest.metadata.country
        return ""

    @rx.var
    def state_or_province(self) -> str:
        """Get the state/province of the current certificate manifest, or an empty string if not set."""
        if self._manifest:
            return self._manifest.metadata.state_or_province
        return ""

    @rx.var
    def locality(self) -> str:
        """Get the locality of the current certificate manifest, or an empty string if not set."""
        if self._manifest:
            return self._manifest.metadata.locality
        return ""

    @rx.var
    def not_before(self) -> datetime:
        """Get the start date (not before) of the current certificate manifest, or the current time if not set."""
        if self._manifest:
            return self._manifest.metadata.not_before
        return datetime.now(UTC)

    @rx.var
    def not_after(self) -> datetime:
        """Get the expiration date (not after) of the current certificate manifest, or the current time if not set."""
        if self._manifest:
            return self._manifest.metadata.not_after
        return datetime.now(UTC)

    @rx.var
    def fingerprint(self) -> str:
        """Get the fingerprint of the current certificate manifest, or an empty string if not set."""
        if self._manifest:
            return self._manifest.metadata.fingerprint
        return ""

    @rx.var
    def key_usage(self) -> list[KeyUsageTypes]:
        """Get the key usage types of the current certificate manifest, or an empty list if not set."""
        if self._manifest:
            return self._manifest.metadata.key_usage
        return []

    @rx.var
    def download_name(self) -> str:
        """Generate a download-friendly filename from the manifest name."""
        if self._manifest:
            return self._manifest.name.replace(" ", "_").lower()
        return ""

    @rx.var
    def certificate_data(self) -> str:
        """Get the certificate PEM data of the current certificate manifest, or an empty string if not set."""
        if self._manifest:
            return self._manifest.metadata.certificate
        return ""

    @rx.var
    def certificate_chain_data(self) -> str:
        """Get the certificate chain PEM data of the current certificate manifest, or an empty string if not set."""
        if self._manifest:
            return f"{self._manifest.metadata.certificate}\n{self._manifest.metadata.chain}"
        return ""

    @rx.var
    def key_data(self) -> str:
        """Get the certificate key PEM data of the current certificate manifest, or an empty string if not set."""
        if self._manifest:
            return self._manifest.get_key()
        return ""

    @rx.var
    def domain_constraint(self) -> str:
        """Get the certificate PEM data of the current certificate manifest, or an empty string if not set."""
        if self._manifest and self._manifest.metadata.domain_constraint:
            return self._manifest.metadata.domain_constraint
        return ""

    @rx.var
    def dns_sans(self) -> str:
        """Get the DNS Subject Alternative Names (SANs) as a newline-separated string, or an empty string if not set."""
        if self._manifest and self._manifest.metadata.san_dns:
            return "\n".join(self._manifest.metadata.san_dns)
        return ""

    @rx.var
    def ip_sans(self) -> str:
        """Get the IP Subject Alternative Names (SANs) as a newline-separated string, or an empty string if not set."""
        if self._manifest and self._manifest.metadata.san_ips:
            return "\n".join(self._manifest.metadata.san_ips)
        return ""

    @rx.event
    async def load(self, name: str) -> None:
        """Open the management dialog for a root certificate authority."""
        self._manifest = CertificateManifest.load(name=name)
