"""Models for PKI certificate management.

This module defines Pydantic models for leaf certificates, intermediate CAs, and X.509 subjects,
including validation patterns and conversion utilities for cryptography.x509 objects.
"""

from ipaddress import ip_address
from typing import Annotated

from cryptography import x509
from cryptography.x509.oid import NameOID
from pydantic import BaseModel, Field

from orbitlab.data_types import KeyUsageTypes


class LeafCertificate(BaseModel):
    """Represents a leaf certificate with associated subject alternative names and server authentication flag.

    Attributes:
        intermediate_ca (str): The name of the intermediate CA that issued this certificate.
        common_name (str): The common name for the certificate subject.
        dns_sans (list[str]): List of DNS Subject Alternative Names.
        ip_sans (list[str]): List of IP Subject Alternative Names.
        server_auth (bool): Indicates if the certificate is for server authentication.
    """

    intermediate_ca: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.\-\* ]{1,64}(?:\.[A-Za-z0-9_.\-\* ]{1,64})*$")]
    common_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.\-\* ]{1,64}(?:\.[A-Za-z0-9_.\-\* ]{1,64})*$")]
    san_dns: Annotated[list[str], Field(default_factory=list)]
    san_ips: Annotated[list[str], Field(default_factory=list)]
    server_auth: Annotated[bool, Field(default=False)]

    @property
    def key_usage(self) -> list[KeyUsageTypes]:
        """Returns the list of key usage types for the certificate based on the server_auth flag.

        Returns:
            list[KeyUsageTypes]: The key usage types applicable to this certificate.
        """
        usages = [KeyUsageTypes.DIGITAL_SIGNATURE, KeyUsageTypes.KEY_AGREEMENT]
        if self.server_auth:
            usages.append(KeyUsageTypes.KEY_ENCIPHERMENT)
        return usages

    def get_x509_san(self) -> x509.SubjectAlternativeName | None:
        """
        Returns an x509.SubjectAlternativeName object if DNS or IP SANs are present, otherwise returns None.

        Returns:
            x509.SubjectAlternativeName | None: The subject alternative name extension or None if no SANs are specified.
        """
        if self.san_dns or self.san_ips:
            return x509.SubjectAlternativeName(
                [x509.DNSName(name) for name in self.san_dns] + [x509.IPAddress(ip_address(ip)) for ip in self.san_ips],
            )
        return None


class IntermediateCA(BaseModel):
    """
    Represents an intermediate Certificate Authority (CA).

    Attributes:
        common_name (str): The common name of the intermediate CA.
        root_ca (str): The root CA associated with this intermediate CA.
        domain_constraint (str): The domain constraint for certificates issued by this CA.
    """

    common_name: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.\-\* ]{1,64}(?:\.[A-Za-z0-9_.\-\* ]{1,64})*$")]
    root_ca: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.\-\* ]{1,64}(?:\.[A-Za-z0-9_.\-\* ]{1,64})*$")]
    domain_constraint: Annotated[
        str,
        Field(pattern=r"^(?:\*\.)?(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$"),
    ]


class Subject(BaseModel):
    """Represents the subject information for an X.509 certificate.

    Attributes:
        common_name (str): The common name of the subject.
        org (str): The organization name.
        org_unit (str): The organizational unit name.
        country (str): The country code (2 uppercase letters).
        state_or_province (str): The state or province name.
        locality (str): The locality name.
    """

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
                x509.NameAttribute(NameOID.COUNTRY_NAME, self.country),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, self.state_or_province),
                x509.NameAttribute(NameOID.LOCALITY_NAME, self.locality),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, self.org),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, self.org_unit),
                x509.NameAttribute(NameOID.COMMON_NAME, self.common_name),
            ],
        )
