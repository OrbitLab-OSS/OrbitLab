"""OrbitLab PKI Management."""

from .pages import certificate_authorities_page, intermediate_certificates_page

__pages__ = (
    certificate_authorities_page,
    intermediate_certificates_page,
)
