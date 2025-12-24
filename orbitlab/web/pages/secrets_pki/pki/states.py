"""OrbitLab PKI Page states."""

from typing import Literal

import reflex as rx

from orbitlab.manifest.secrets import CertificateManifest
from orbitlab.web.states.manifests import ManifestsState


class CAState(ManifestsState):
    """State for managing Certificate Authorities."""

    cert_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var
    def filtered_certificates(self) -> list[CertificateManifest]:
        """Filter certificate authorities based on the current filter setting."""
        if self.cert_filter == "All":
            return self.certificate_authorities
        return [ca for ca in self.certificate_authorities if ca.metadata.status == self.cert_filter.lower()]


class IntermediateCAState(ManifestsState):
    """State for managing Certificate Authorities."""

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
