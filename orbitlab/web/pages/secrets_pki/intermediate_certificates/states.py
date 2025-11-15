from typing import Literal

import reflex as rx

from orbitlab.data_types import CertificateTypes, ManifestKind
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.secrets import CertificateManifest


class LoadCertificates:
    @classmethod
    def __load__(cls, cert_type: CertificateTypes) -> list[CertificateManifest]:
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
        return cls.__load__(CertificateTypes.INTERMEDIATE)

    @classmethod
    def certificate_authorities(cls) -> list[str]:
        return [cert.name for cert in cls.__load__(CertificateTypes.ROOT)]


class IntermediateCAState(rx.State):
    """State for managing Certificate Authorities."""

    intermediate_certificates: list[CertificateManifest] = rx.field(default_factory=LoadCertificates.intermediate)
    root_certificates: list[str] = rx.field(default_factory=LoadCertificates.certificate_authorities)
    cert_filter: Literal["All", "Valid", "Warning", "Expired"] = "All"

    @rx.var
    def filtered_certificates(self) -> list[CertificateManifest]:
        if self.cert_filter == "All":
            return self.intermediate_certificates
        return [ca for ca in self.intermediate_certificates if ca.metadata.status == self.cert_filter.lower()]


class ManageIntermediateCerts(rx.State):
    manifest: CertificateManifest | None = None
    revoke_disabled: bool = True
