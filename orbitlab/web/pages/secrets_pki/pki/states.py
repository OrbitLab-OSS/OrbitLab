"""OrbitLab PKI Page states."""

from datetime import UTC, datetime
from typing import Literal

import reflex as rx

from orbitlab.data_types import KeyUsageTypes
from orbitlab.manifest.pki import IntermediateCertificateManifest, LeafCertificateManifest, RootCertificateManifest
from orbitlab.web.utilities import CacheBuster


class RootCertificatesState(CacheBuster, rx.State):
    """State for managing Root Certificate Authorities."""

    cert_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var(deps=["_cached_all"])
    def all(self) -> list[RootCertificateManifest]:
        """Get all root certificate authority manifests from the certificates list."""
        return [RootCertificateManifest.load(name=name) for name in RootCertificateManifest.get_existing()]

    @rx.var
    def select_options(self) -> dict[str, str]:
        """Get a list of certificate authority names."""
        return {cert.spec.subject.common_name: cert.name for cert in self.all}

    @rx.var
    def filtered(self) -> list[RootCertificateManifest]:
        """Filter certificate authorities based on the current filter setting."""
        if self.cert_filter == "All":
            return self.all
        return [ca for ca in self.all if ca.status == self.cert_filter.lower()]


class IntermediateCertificatesState(CacheBuster, rx.State):
    """State for managing Intermediate Certificate Authorities."""

    cert_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var(deps=["_cached_all"])
    def all(self) -> list[IntermediateCertificateManifest]:
        """Get all intermediate certificate authority manifests from the certificates list."""
        return [
            IntermediateCertificateManifest.load(name=name) for name in IntermediateCertificateManifest.get_existing()
        ]

    @rx.var
    def select_options(self) -> dict[str, str]:
        """Get a list of intermediate certificate authority names."""
        return {cert.spec.subject.common_name: cert.name for cert in self.all}

    @rx.var
    def filtered(self) -> list[IntermediateCertificateManifest]:
        """Filter certificate authorities based on the current filter setting."""
        if self.cert_filter == "All":
            return self.all
        return [ca for ca in self.all if ca.status == self.cert_filter.lower()]


class LeafCertificatesState(CacheBuster, rx.State):
    """State for managing Leaf Certificates."""

    cert_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var(deps=["_cached_all"])
    def all(self) -> list[LeafCertificateManifest]:
        """Get all leaf certificate manifests from the certificates list."""
        return [
            LeafCertificateManifest.load(name=name) for name in LeafCertificateManifest.get_existing()
        ]

    @rx.var
    def names(self) -> list[str]:
        """Get a list of intermediate certificate authority names."""
        return [cert.name for cert in self.all]

    @rx.var
    def filtered(self) -> list[LeafCertificateManifest]:
        """Filter certificate authorities based on the current filter setting."""
        if self.cert_filter == "All":
            return self.all
        return [ca for ca in self.all if ca.status == self.cert_filter.lower()]


class ManageRootCertificateState(rx.State):
    """State for managing individual Certificate Authority operations."""

    manifest: RootCertificateManifest | None = None
    delete_disabled: bool = True

    @rx.var
    def id(self) -> str:
        """Get the ID of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.name
        return ""

    @rx.var
    def common_name(self) -> str:
        """Get the common name of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.common_name
        return ""

    @rx.var
    def issuer(self) -> str:
        """Get the issuer of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            if self.manifest.spec.subject.common_name == self.manifest.spec.issued.issuer:
                return "Self"
            return self.manifest.spec.issued.issuer
        return ""

    @rx.var
    def serial_number(self) -> str:
        """Get the serial number of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.issued.serial_number
        return ""

    @rx.var
    def org(self) -> str:
        """Get the organization of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.org
        return ""

    @rx.var
    def org_unit(self) -> str:
        """Get the organizational unit of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.org_unit
        return ""

    @rx.var
    def country(self) -> str:
        """Get the counter of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.country
        return ""

    @rx.var
    def state_or_province(self) -> str:
        """Get the state/province of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.state_or_province
        return ""

    @rx.var
    def locality(self) -> str:
        """Get the locality of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.locality
        return ""

    @rx.var
    def not_before(self) -> datetime:
        """Get the start date (not before) of the current certificate manifest, or the current time if not set."""
        if self.manifest:
            return self.manifest.spec.issued.not_before
        return datetime.now(UTC)

    @rx.var
    def not_after(self) -> datetime:
        """Get the expiration date (not after) of the current certificate manifest, or the current time if not set."""
        if self.manifest:
            return self.manifest.spec.issued.not_after
        return datetime.now(UTC)

    @rx.var
    def fingerprint(self) -> str:
        """Get the fingerprint of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.issued.fingerprint
        return ""

    @rx.var
    def key_usage(self) -> list[KeyUsageTypes]:
        """Get the key usage types of the current certificate manifest, or an empty list if not set."""
        if self.manifest:
            return self.manifest.spec.key_usage
        return []

    @rx.var
    def download_name(self) -> str:
        """Generate a download-friendly filename from the manifest name."""
        if self.manifest:
            return self.manifest.spec.subject.common_name.replace(" ", "_").lower()
        return ""

    @rx.var
    def certificate_data(self) -> str:
        """Get the certificate PEM data of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.issued.certificate
        return ""


class ManageIntermediateCertificateState(rx.State):
    """State for managing individual Certificate Authority operations."""

    manifest: IntermediateCertificateManifest | None = None
    delete_disabled: bool = True

    @rx.var
    def id(self) -> str:
        """Get the ID of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.name
        return ""

    @rx.var
    def common_name(self) -> str:
        """Get the common name of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.common_name
        return ""

    @rx.var
    def issuer(self) -> str:
        """Get the issuer of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.issued.issuer
        return ""

    @rx.var
    def serial_number(self) -> str:
        """Get the serial number of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.issued.serial_number
        return ""

    @rx.var
    def org(self) -> str:
        """Get the organization of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.org
        return ""

    @rx.var
    def org_unit(self) -> str:
        """Get the organizational unit of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.org_unit
        return ""

    @rx.var
    def country(self) -> str:
        """Get the counter of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.country
        return ""

    @rx.var
    def state_or_province(self) -> str:
        """Get the state/province of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.state_or_province
        return ""

    @rx.var
    def locality(self) -> str:
        """Get the locality of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.locality
        return ""

    @rx.var
    def not_before(self) -> datetime:
        """Get the start date (not before) of the current certificate manifest, or the current time if not set."""
        if self.manifest:
            return self.manifest.spec.issued.not_before
        return datetime.now(UTC)

    @rx.var
    def not_after(self) -> datetime:
        """Get the expiration date (not after) of the current certificate manifest, or the current time if not set."""
        if self.manifest:
            return self.manifest.spec.issued.not_after
        return datetime.now(UTC)

    @rx.var
    def fingerprint(self) -> str:
        """Get the fingerprint of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.issued.fingerprint
        return ""

    @rx.var
    def domain_constraint(self) -> str:
        """Get the key usage types of the current certificate manifest, or an empty list if not set."""
        if self.manifest:
            return self.manifest.metadata.domain_constraint
        return ""

    @rx.var
    def download_name(self) -> str:
        """Generate a download-friendly filename from the manifest name."""
        if self.manifest:
            return self.manifest.spec.subject.common_name.replace(" ", "_").lower()
        return ""

    @rx.var
    def certificate_data(self) -> str:
        """Get the certificate PEM data of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.issued.certificate
        return ""

    @rx.var
    def certificate_chain_data(self) -> str:
        """Get the certificate chain PEM data of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return f"{self.manifest.spec.issued.certificate}\n{self.manifest.spec.issued.chain}"
        return ""


class ManageLeafCertificateState(rx.State):
    """State for managing individual Leaf Certificate operations."""

    manifest: LeafCertificateManifest | None = None
    revoke_disabled: bool = True
    delete_disabled: bool = True

    @rx.var
    def id(self) -> str:
        """Get the ID of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.name
        return ""

    @rx.var
    def common_name(self) -> str:
        """Get the common name of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.common_name
        return ""

    @rx.var
    def issuer(self) -> str:
        """Get the issuer of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.issued.issuer
        return ""

    @rx.var
    def serial_number(self) -> str:
        """Get the serial number of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.issued.serial_number
        return ""

    @rx.var
    def org(self) -> str:
        """Get the organization of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.org
        return ""

    @rx.var
    def org_unit(self) -> str:
        """Get the organizational unit of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.org_unit
        return ""

    @rx.var
    def country(self) -> str:
        """Get the counter of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.country
        return ""

    @rx.var
    def state_or_province(self) -> str:
        """Get the state/province of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.state_or_province
        return ""

    @rx.var
    def locality(self) -> str:
        """Get the locality of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.subject.locality
        return ""

    @rx.var
    def not_before(self) -> datetime:
        """Get the start date (not before) of the current certificate manifest, or the current time if not set."""
        if self.manifest:
            return self.manifest.spec.issued.not_before
        return datetime.now(UTC)

    @rx.var
    def not_after(self) -> datetime:
        """Get the expiration date (not after) of the current certificate manifest, or the current time if not set."""
        if self.manifest:
            return self.manifest.spec.issued.not_after
        return datetime.now(UTC)

    @rx.var
    def fingerprint(self) -> str:
        """Get the fingerprint of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.issued.fingerprint
        return ""

    @rx.var
    def download_name(self) -> str:
        """Generate a download-friendly filename from the manifest name."""
        if self.manifest:
            return self.manifest.spec.subject.common_name.replace(" ", "_").lower()
        return ""

    @rx.var
    def certificate_data(self) -> str:
        """Get the certificate PEM data of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.spec.issued.certificate
        return ""

    @rx.var
    def certificate_chain_data(self) -> str:
        """Get the certificate chain PEM data of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return f"{self.manifest.spec.issued.certificate}\n{self.manifest.spec.issued.chain}"
        return ""

    @rx.var
    def key_data(self) -> str:
        """Get the certificate key PEM data of the current certificate manifest, or an empty string if not set."""
        if self.manifest:
            return self.manifest.get_key()
        return ""

    @rx.var
    def dns_sans(self) -> str:
        """Get the DNS Subject Alternative Names (SANs) as a newline-separated string, or an empty string if not set."""
        if self.manifest and self.manifest.metadata.san_dns:
            return "\n".join(self.manifest.metadata.san_dns)
        return ""

    @rx.var
    def ip_sans(self) -> str:
        """Get the IP Subject Alternative Names (SANs) as a newline-separated string, or an empty string if not set."""
        if self.manifest and self.manifest.metadata.san_ips:
            return "\n".join(self.manifest.metadata.san_ips)
        return ""
