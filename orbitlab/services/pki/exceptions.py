"""Custom exception classes for PKI and SSH key management in the OrbitLab services."""

from orbitlab.data_types import CertificateTypes


class CSRExistsError(Exception):
    """Exception raised when a CSR with the specified name already exists or does not exist.

    Attributes:
        name (str): The name of the certificate signing request.
        exists (bool): Indicates whether the CSR already exists.
    """
    def __init__(self, name: str, *, exists: bool) -> None:
        """Initialize CSRExistsError.

        Args:
            name (str): The name of the certificate signing request.
            exists (bool): Indicates whether the CSR already exists.
        """
        super().__init__(
            f"Certificate Signing Request for '{name}' already exists."
            if exists else f"Certificate Signing Request for '{name}' does not exists.",
        )
        self.name = name


class CSRSigningError(Exception):
    """Exception raised when there is an error signing a certificate signing request (CSR).

    Attributes:
        msg (str): The error message describing the signing error.
    """
    def __init__(self, msg: str) -> None:
        """Initialize CSRSigningError.

        Args:
            msg (str): The error message describing the signing error.
        """
        super().__init__(msg)
        self.msg = msg


class CertificateExistsError(Exception):
    """Exception raised when a certificate with the specified name already exists or does not exist.

    Attributes:
        name (str): The name of the certificate.
        exists (bool): Indicates whether the certificate already exists.
    """
    def __init__(self, name: str, *, exists: bool) -> None:
        """
        Initialize CertificateExistsError.

        Args:
            name (str): The name of the certificate.
            exists (bool): Indicates whether the certificate already exists.
        """
        super().__init__(
            f"Certificate '{name}' already exists."
            if exists else f"Certificate '{name}' does not exists.",
        )
        self.name = name


class CertificateTypeError(Exception):
    """Exception raised when a certificate is not of the expected type.

    Attributes:
        common_name (str): The common name of the certificate.
        cert_type (CertificateTypes): The expected certificate type.
    """
    def __init__(self, common_name: str, cert_type: CertificateTypes) -> None:
        """Initialize CertificateTypeError.

        Args:
            common_name (str): The common name of the certificate.
            cert_type (CertificateTypes): The expected certificate type.
        """
        super().__init__(f"Certificate {common_name} not of type {cert_type}")
        self.common_name = common_name
        self.cert_type = cert_type


class CertificateFingerprintError(Exception):
    """Exception raised when a certificate's fingerprint does not match.

    Attributes:
        common_name (str): The common name of the certificate.
        serial_number (str): The serial number of the certificate.
    """
    def __init__(self, common_name: str, serial_number: str) -> None:
        """
        Initialize CertificateFingerprintError.

        Args:
            common_name (str): The common name of the certificate.
            serial_number (str): The serial number of the certificate.
        """
        super().__init__(f"Certificate {common_name} ({serial_number}) fingerprint does not match.")
        self.common_name = common_name
        self.serial_number = serial_number


class SSHKeyExistsError(Exception):
    """Exception raised when an SSH key with the specified name already exists or does not exist.

    Attributes:
        name (str): The name of the SSH key.
        exists (bool): Indicates whether the SSH key already exists.
    """
    def __init__(self, name: str, *, exists: bool) -> None:
        """
        Initialize SSHKeyExistsError.

        Args:
            name (str): The name of the SSH key.
            exists (bool): Whether the SSH key already exists.
        """
        super().__init__(
            f"SSH Key with name {name} already exists."
            if exists else f"SSH Key with name {name} does not exists.",
        )
        self.name = name
