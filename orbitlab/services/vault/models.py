"""Models for secrets stored in the vault."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, SecretStr, field_serializer


class Secret(BaseModel):
    """Represents a secret stored in the vault.

    Attributes:
        name (str): The name of the secret.
        secret_string (SecretStr): The secret value.
        created_at (datetime): The creation timestamp.
        version (int): The version number of the secret.
        checksum (str): The SHA-256 checksum of the secret.
        updated_at (datetime | None): The last update timestamp.
        metadata (dict[str, str]): Additional metadata for the secret.
    """
    name: str
    secret_string: SecretStr
    created_at: datetime
    version: int
    checksum: str
    updated_at: Annotated[datetime | None, Field(default=None)]
    metadata: Annotated[dict[str, str], Field(default_factory=dict)]

    @field_serializer("secret_string", when_used="json")
    def dump_secret(self, secret_string: SecretStr) -> str:
        """Serialize the secret string for JSON output.

        Args:
            secret_string (SecretStr): The secret value to serialize.

        Returns:
            str: The plain secret string value.
        """
        return secret_string.get_secret_value()
