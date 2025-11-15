from typing import Literal, overload

import reflex as rx

from orbitlab.data_types import CertificateTypes, ManifestKind
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.secrets import CertificateManifest


@overload
def get_certificates_by_type(cert_type: CertificateTypes, *, name_only: Literal[True]) -> list[str]: ...


@overload
def get_certificates_by_type(
    cert_type: CertificateTypes,
    *,
    name_only: Literal[False],
) -> list[CertificateManifest]: ...


def get_certificates_by_type(
    cert_type: CertificateTypes,
    *,
    name_only: bool = False,
) -> list[str | CertificateManifest]:
    """Get certificates filtered by type.

    Args:
        cert_type (CertificateTypes): The type of certificates to retrieve.
        name_only (bool): If True, return only certificate names. If False, return full CertificateManifest objects.
            Defaults to False.

    Returns:
        A list of certificate names if name_only is True, otherwise a list of CertificateManifest objects.
    """
    client = ManifestClient()
    certificates = []
    for certificate in client.get_existing_by_kind(kind=ManifestKind.CERTIFICATE):
        cert = client.load(certificate, kind=ManifestKind.CERTIFICATE)
        if cert.metadata.type == cert_type:
            if name_only:
                certificates.append(cert.name)
            else:
                certificates.append(cert)
    return certificates


class CertificateManifestsState(rx.State):
    """State management for certificate manifests.

    Attributes:
        root_certificate_names: A list of root certificate names.
        root_certificate_manifests: A list of root certificate manifest objects.
    """

    root_certificate_names: list[str] = rx.field(
        default_factory=lambda: get_certificates_by_type(CertificateTypes.ROOT, name_only=True),
    )
    root_certificate_manifests: list[CertificateManifest] = rx.field(
        default_factory=lambda: get_certificates_by_type(CertificateTypes.ROOT),
    )

    @rx.event
    async def refresh_root_certificates(self) -> None:
        self.root_certificate_names = get_certificates_by_type(CertificateTypes.ROOT, name_only=True)
        self.root_certificate_manifests = get_certificates_by_type(CertificateTypes.ROOT)
