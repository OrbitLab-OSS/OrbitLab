from typing import Literal

import reflex as rx

from orbitlab.data_types import CertificateTypes, ManifestKind
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.secrets import CertificateManifest


def load_certificate_authorities() -> list[CertificateManifest]:
    client = ManifestClient()
    certs = list(client.get_existing_by_kind(kind=ManifestKind.CERTIFICATE).keys())
    certificate_authorities = []
    for cert in certs:
        manifest: CertificateManifest = client.load(cert, kind=ManifestKind.CERTIFICATE)
        if manifest.metadata.type == CertificateTypes.ROOT:
            certificate_authorities.append(manifest)
    return certificate_authorities


class CAState(rx.State):
    """State for managing Certificate Authorities."""

    certificate_authorities: list[CertificateManifest] = rx.field(default_factory=load_certificate_authorities)
    ca_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var
    def filtered_cas(self) -> list[CertificateManifest]:
        if self.ca_filter == "All":
            return self.certificate_authorities
        return [ca for ca in self.certificate_authorities if ca.metadata.status == self.ca_filter.lower()]


class ManageCA(rx.State):
    manifest: CertificateManifest | None = None
    revoke_disabled: bool = True

    @rx.var
    def download_name(self) -> str:
        if self.manifest:
            return self.manifest.name.replace(" ", "_").lower()
        return ""
