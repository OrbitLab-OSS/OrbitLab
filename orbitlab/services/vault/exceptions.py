"""Custom exception classes for secret management in the Vault service.

This module defines exceptions for handling secret not found, invalid checksum,
secret existence conflicts, and rollback errors.
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Secret


class SecretNotFoundError(Exception):
    """Exception raised when a secret file path cannot be found.

    Attributes:
        secret (str): The secret whose file path was not found.
        version (int): The version of the secret.
    """

    def __init__(self, secret_name: Path, version: int) -> None:
        """Initialize the SecretNotFoundError with the secret and version whose file path was not found.

        Args:
            secret_name (str | Path): The secret whose file path was not found.
            version (int): The version of the secret.
        """
        super().__init__(f"File path for {secret_name!s} version {version} not found.")
        self.secret_name = secret_name
        self.version = version


class InvalidChecksumError(Exception):
    """Exception raised when a secret's checksum is invalid.

    Attributes:
        secret (Secret): The Secret object with an invalid checksum.
    """

    def __init__(self, secret: "Secret", checksum: str) -> None:
        """Initialize the InvalidChecksumError with the secret that has an invalid checksum.

        Args:
            secret (Secret): The Secret object with an invalid checksum.
            checksum (str): The checksum that was found to be invalid.
        """
        super().__init__(f"Checksum {checksum} does not match {secret.checksum} for secret {secret.name}")
        self.secret = secret


class SecretExistsError(Exception):
    """Exception raised when attempting to create a secret that already exists.

    Attributes:
        secret_name (Path): The name/path of the secret that already exists.
    """

    def __init__(self, secret_name: Path) -> None:
        """Initialize the SecretExistsError with the secret name that already exists.

        Args:
            secret_name (Path): The name/path of the secret that already exists.
        """
        super().__init__(f"Secret {secret_name!s} already exists.")
        self.secret_name = secret_name


class SecretRollbackError(Exception):
    """Exception raised when a rollback operation on a secret fails.

    Attributes:
        msg (str): The error message describing the rollback issue.
    """

    def __init__(self, msg: str) -> None:
        """Initialize the SecretRollbackError with a message.

        Args:
            msg (str): The error message describing the rollback issue.
        """
        super().__init__(msg)
        self.msg = msg
