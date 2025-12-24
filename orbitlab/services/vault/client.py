"""SecretVault module for securely storing, encrypting, and managing secrets using AES-GCM encryption."""

import base64
import hashlib
import os
import secrets
import shutil
import string
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from pydantic import SecretStr

from orbitlab.constants import Directories

from .exceptions import InvalidChecksumError, SecretExistsError, SecretNotFoundError, SecretRollbackError
from .models import Secret


class SecretVault:
    """A vault for securely storing, encrypting, and managing secrets using AES-GCM encryption."""

    def __init__(self) -> None:
        """Initialize the SecretVault with default cryptographic parameters."""
        self.iterations = 200000
        self.__check__()

    @cached_property
    def master_key(self) -> str:
        """Return the master key for the vault from the environment variable."""
        return os.environ.get("ORBITLAB_VAULT_KEY", "")

    def __check__(self) -> None:
        """Check if the secrets root directory exists and the master key is set."""
        if not self.master_key:
            msg = "Missing master key. Did you set `ORBITLAB_VAULT_KEY`?"
            raise RuntimeError(msg)

    def __derive_key__(self, salt: bytes) -> bytes:
        """Derive a cryptographic key from the master key and salt using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.iterations,
        )
        return kdf.derive(self.master_key.encode())

    def __encrypt__(self, secret: Secret) -> bytes:
        """Encrypt a Secret object using AES-GCM and return the encrypted bytes."""
        data = secret.model_dump_json().encode()
        salt = secrets.token_bytes(16)
        key = AESGCM(self.__derive_key__(salt))
        nonce = secrets.token_bytes(12)
        cipher_text = key.encrypt(nonce, data, None)
        return base64.b64encode(salt + nonce + cipher_text)

    def __decrypt__(self, blob: bytes) -> str:
        """Decrypt an encrypted blob using AES-GCM and return the plaintext string."""
        raw = base64.b64decode(blob)
        salt, nonce, cipher_text = raw[:16], raw[16:28], raw[28:]
        key = AESGCM(self.__derive_key__(salt))
        return key.decrypt(nonce, cipher_text, None).decode()

    def __load__(self, filepath: Path) -> Secret:
        """Load and decrypt a secret from the specified file path."""
        with filepath.open("rb") as f:
            secret = Secret.model_validate_json(self.__decrypt__(f.read()))

        checksum = self.__get_checksum__(secret)
        if not checksum == secret.checksum:
            raise InvalidChecksumError(secret=secret, checksum=checksum)

        return secret

    def __save__(self, filepath: Path, secret: Secret) -> None:
        """Save an encrypted Secret object to the specified file path."""
        checksum = self.__get_checksum__(secret=secret)
        secret.checksum = checksum
        with filepath.open("+wb") as f:
            f.write(self.__encrypt__(secret))

    def __get_checksum__(self, secret: Secret) -> str:
        """Compute and return the SHA-256 checksum of the secret."""
        return hashlib.sha256(secret.secret_string.get_secret_value().encode()).hexdigest()

    def __get_file_path__(self, secret_name: Path, version: int) -> Path:
        """Generate and return the file path for a secret based on its path and version."""
        string_path = secret_name.as_posix()
        digest = hashlib.sha256(string_path.encode()).hexdigest()
        secret_path = "/".join([digest[i : i + 2] for i in range(0, len(string_path.split("/")) * 2, 2)])
        full_path = Directories.VAULT / Path(secret_path) / f"{digest[-10:]}.v{version}.enc"
        full_path.parent.mkdir(parents=True, exist_ok=True)
        return full_path

    @classmethod
    def generate_random_password(
        cls,
        length: int = 16,
        min_lower: int = 3,
        min_upper: int = 3,
        min_digits: int = 3,
    ) -> str:
        """Generate a random password with specified character requirements."""
        alphabet = string.ascii_letters + string.digits
        while True:
            password = "".join(secrets.choice(alphabet) for _ in range(length))
            if (
                sum(c.islower() for c in password) >= min_lower and
                sum(c.isupper() for c in password) >= min_upper and
                sum(c.isdigit() for c in password) >= min_digits
            ):
                break
        return password

    def create(self, secret_name: Path, value: str, metadata: dict[str, str] | None = None) -> int:
        """Create a new secret in the vault with the given name, value, and optional metadata."""
        if not metadata:
            metadata = {}

        version = 1
        filepath = self.__get_file_path__(secret_name=secret_name, version=version)
        if filepath.exists():
            raise SecretExistsError(secret_name=secret_name)

        secret = Secret(
            name=str(secret_name),
            secret_string=value, # pyright: ignore[reportArgumentType]
            created_at=datetime.now(UTC),
            version=version,
            checksum="",  # Checksum is computed and updated on __save__()
            metadata=metadata,
        )
        self.__save__(filepath=filepath, secret=secret)
        return version

    def get(self, secret_name: Path | str, version: int) -> Secret:
        """Retrieve a secret from the vault by its name and version."""
        if isinstance(secret_name, str):
            secret_name = Path(secret_name)

        filepath = self.__get_file_path__(secret_name=secret_name, version=version)
        if not filepath.exists():
            raise SecretNotFoundError(secret_name=secret_name, version=version)

        return self.__load__(filepath=filepath)

    def update(self, secret_name: Path, version: int, value: str, metadata: dict[str, str] | None = None) -> int:
        """Update an existing secret with a new value and metadata, incrementing its version."""
        filepath = self.__get_file_path__(secret_name=secret_name, version=version)
        if not filepath.exists():
            raise SecretNotFoundError(secret_name=secret_name, version=version)

        secret = self.__load__(filepath=filepath)
        secret.secret_string = SecretStr(value)
        secret.version += 1
        secret.updated_at = datetime.now(UTC)
        if metadata:
            secret.metadata = metadata
        new_filepath = self.__get_file_path__(secret_name=secret_name, version=secret.version)
        self.__save__(filepath=new_filepath, secret=secret)
        return secret.version

    def rollback(self, secret_name: Path, current_version: int, rollback_version: int) -> int:
        """Rollback a secret to a previous version by deleting newer versions."""
        if not rollback_version < current_version:
            raise SecretRollbackError(msg=f"Version {rollback_version} is not less than {current_version}")

        filepath = self.__get_file_path__(secret_name=secret_name, version=current_version)
        if not filepath.exists():
            raise SecretNotFoundError(secret_name=secret_name, version=current_version)

        for version in range(rollback_version + 1, current_version):
            filepath = self.__get_file_path__(secret_name=secret_name, version=version)
            filepath.unlink()

        return rollback_version

    def delete(self, secret_name: Path) -> None:
        """Delete a secret and all its versions from the vault."""
        # version doesn't actually matter, we just need the parent directory.
        filepath = self.__get_file_path__(secret_name=secret_name, version=1)
        if filepath.exists():
            shutil.rmtree(filepath.parent)
