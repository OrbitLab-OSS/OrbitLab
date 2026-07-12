"""OrbitLab PKI Page states."""

from datetime import UTC, datetime
from typing import Literal

import reflex as rx

from orbitlab.data_types import KeyUsageTypes
from orbitlab.redis.clients import SecretsClient
from orbitlab.redis.models import IntermediateCert, LeafCert, RootCert
from orbitlab.web.global_state import OrbitLabState


class RootCertificatesState(OrbitLabState):
    """State for managing Root Certificate Authorities."""

    cert_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var
    def select_options(self) -> list[str]:
        return [cert.subject.common_name for cert in self.root_certificates]

    @rx.var
    def filtered(self) -> list[RootCert]:
        """Filter certificate authorities based on the current filter setting."""
        if self.cert_filter == "All":
            return self.root_certificates
        return [ca for ca in self.root_certificates if ca.status == self.cert_filter.lower()]


class IntermediateCertificatesState(OrbitLabState):
    """State for managing Intermediate Certificate Authorities."""

    cert_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var
    def select_options(self) -> list[str]:
        """Get a list of intermediate certificate authority names."""
        return [cert.subject.common_name for cert in self.intermediate_certificates]

    @rx.var
    def filtered(self) -> list[IntermediateCert]:
        """Filter certificate authorities based on the current filter setting."""
        if self.cert_filter == "All":
            return self.intermediate_certificates
        return [ca for ca in self.intermediate_certificates if ca.status == self.cert_filter.lower()]


class LeafCertificatesState(OrbitLabState):
    """State for managing Leaf Certificates."""

    cert_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var
    def names(self) -> list[str]:
        """Get a list of intermediate certificate authority names."""
        return [cert.subject.common_name for cert in self.leaf_certificates]

    @rx.var
    def filtered(self) -> list[LeafCert]:
        """Filter certificate authorities based on the current filter setting."""
        if self.cert_filter == "All":
            return self.leaf_certificates
        return [ca for ca in self.leaf_certificates if ca.status == self.cert_filter.lower()]


class ManageRootCertificateState(rx.State):
    """State for managing individual Certificate Authority operations."""

    cert: RootCert | None = None
    delete_disabled: bool = True

    @rx.var
    def common_name(self) -> str:
        """Get the common name of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.common_name
        return ""

    @rx.var
    def issuer(self) -> str:
        """Get the issuer of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            if self.cert.subject.common_name == self.cert.issuer:
                return "Self"
            return self.cert.issuer
        return ""

    @rx.var
    def serial_number(self) -> str:
        """Get the serial number of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.serial_number
        return ""

    @rx.var
    def org(self) -> str:
        """Get the organization of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.org
        return ""

    @rx.var
    def org_unit(self) -> str:
        """Get the organizational unit of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.org_unit
        return ""

    @rx.var
    def country(self) -> str:
        """Get the counter of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.country
        return ""

    @rx.var
    def state_or_province(self) -> str:
        """Get the state/province of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.state_or_province
        return ""

    @rx.var
    def locality(self) -> str:
        """Get the locality of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.locality
        return ""

    @rx.var
    def not_before(self) -> datetime:
        """Get the start date (not before) of the current certificate manifest, or the current time if not set."""
        if self.cert:
            return self.cert.not_before
        return datetime.now(UTC)

    @rx.var
    def not_after(self) -> datetime:
        """Get the expiration date (not after) of the current certificate manifest, or the current time if not set."""
        if self.cert:
            return self.cert.not_after
        return datetime.now(UTC)

    @rx.var
    def fingerprint(self) -> str:
        """Get the fingerprint of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.fingerprint
        return ""

    @rx.var
    def key_usage(self) -> list[KeyUsageTypes]:
        """Get the key usage types of the current certificate manifest, or an empty list if not set."""
        if self.cert:
            return self.cert.key_usage
        return []

    @rx.var
    def download_name(self) -> str:
        """Generate a download-friendly filename from the manifest name."""
        if self.cert:
            return self.cert.subject.common_name.replace(" ", "_").lower()
        return ""

    @rx.var
    def certificate_data(self) -> str:
        """Get the certificate PEM data of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.certificate
        return ""


class ManageIntermediateCertificateState(rx.State):
    """State for managing individual Certificate Authority operations."""

    cert: IntermediateCert | None = None
    delete_disabled: bool = True

    @rx.var
    def common_name(self) -> str:
        """Get the common name of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.common_name
        return ""

    @rx.var
    def issuer(self) -> str:
        """Get the issuer of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.issuer
        return ""

    @rx.var
    def serial_number(self) -> str:
        """Get the serial number of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.serial_number
        return ""

    @rx.var
    def org(self) -> str:
        """Get the organization of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.org
        return ""

    @rx.var
    def org_unit(self) -> str:
        """Get the organizational unit of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.org_unit
        return ""

    @rx.var
    def country(self) -> str:
        """Get the counter of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.country
        return ""

    @rx.var
    def state_or_province(self) -> str:
        """Get the state/province of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.state_or_province
        return ""

    @rx.var
    def locality(self) -> str:
        """Get the locality of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.locality
        return ""

    @rx.var
    def not_before(self) -> datetime:
        """Get the start date (not before) of the current certificate manifest, or the current time if not set."""
        if self.cert:
            return self.cert.not_before
        return datetime.now(UTC)

    @rx.var
    def not_after(self) -> datetime:
        """Get the expiration date (not after) of the current certificate manifest, or the current time if not set."""
        if self.cert:
            return self.cert.not_after
        return datetime.now(UTC)

    @rx.var
    def fingerprint(self) -> str:
        """Get the fingerprint of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.fingerprint
        return ""

    @rx.var
    def domain_constraint(self) -> str:
        """Get the key usage types of the current certificate manifest, or an empty list if not set."""
        if self.cert:
            return self.cert.domain_constraint
        return ""

    @rx.var
    def download_name(self) -> str:
        """Generate a download-friendly filename from the manifest name."""
        if self.cert:
            return self.cert.subject.common_name.replace(" ", "_").lower()
        return ""

    @rx.var
    def certificate_data(self) -> str:
        """Get the certificate PEM data of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.certificate
        return ""

    @rx.var
    def certificate_chain_data(self) -> str:
        """Get the certificate chain PEM data of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return f"{self.cert.certificate}\n{self.cert.chain}"
        return ""


class ManageLeafCertificateState(rx.State):
    """State for managing individual Leaf Certificate operations."""

    cert: LeafCert | None = None
    revoke_disabled: bool = True
    delete_disabled: bool = True

    @rx.var
    def common_name(self) -> str:
        """Get the common name of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.common_name
        return ""

    @rx.var
    def issuer(self) -> str:
        """Get the issuer of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.issuer
        return ""

    @rx.var
    def serial_number(self) -> str:
        """Get the serial number of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.serial_number
        return ""

    @rx.var
    def org(self) -> str:
        """Get the organization of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.org
        return ""

    @rx.var
    def org_unit(self) -> str:
        """Get the organizational unit of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.org_unit
        return ""

    @rx.var
    def country(self) -> str:
        """Get the counter of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.country
        return ""

    @rx.var
    def state_or_province(self) -> str:
        """Get the state/province of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.state_or_province
        return ""

    @rx.var
    def locality(self) -> str:
        """Get the locality of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.subject.locality
        return ""

    @rx.var
    def not_before(self) -> datetime:
        """Get the start date (not before) of the current certificate manifest, or the current time if not set."""
        if self.cert:
            return self.cert.not_before
        return datetime.now(UTC)

    @rx.var
    def not_after(self) -> datetime:
        """Get the expiration date (not after) of the current certificate manifest, or the current time if not set."""
        if self.cert:
            return self.cert.not_after
        return datetime.now(UTC)

    @rx.var
    def fingerprint(self) -> str:
        """Get the fingerprint of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.fingerprint
        return ""

    @rx.var
    def download_name(self) -> str:
        """Generate a download-friendly filename from the manifest name."""
        if self.cert:
            return self.cert.subject.common_name.replace(" ", "_").lower()
        return ""

    @rx.var
    def certificate_data(self) -> str:
        """Get the certificate PEM data of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return self.cert.certificate
        return ""

    @rx.var
    def certificate_chain_data(self) -> str:
        """Get the certificate chain PEM data of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return f"{self.cert.certificate}\n{self.cert.chain}"
        return ""

    @rx.var
    async def key_data(self) -> str:
        """Get the certificate key PEM data of the current certificate manifest, or an empty string if not set."""
        if self.cert:
            return await SecretsClient().get_private_key(cert_common_name=self.cert.subject.common_name)
        return ""

    @rx.var
    def dns_sans(self) -> str:
        """Get the DNS Subject Alternative Names (SANs) as a newline-separated string, or an empty string if not set."""
        if self.cert and self.cert.san_dns:
            return "\n".join(self.cert.san_dns)
        return ""

    @rx.var
    def ip_sans(self) -> str:
        """Get the IP Subject Alternative Names (SANs) as a newline-separated string, or an empty string if not set."""
        if self.cert and self.cert.san_ips:
            return "\n".join(self.cert.san_ips)
        return ""
