"""Custom exception classes for PKI and SSH key management in the OrbitLab services."""


class CertificateFingerprintError(Exception):
    """Exception raised when a certificate's fingerprint does not match."""

    def __init__(self, serial_number: str) -> None:
        """Initialize CertificateFingerprintError."""
        super().__init__(f"Certificate {serial_number} fingerprint does not match.")
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
            f"SSH Key with name {name} already exists." if exists else f"SSH Key with name {name} does not exists.",
        )
        self.name = name
