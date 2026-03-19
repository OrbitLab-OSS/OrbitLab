"""This module provides classes and functions for managing X.509 certificates, CSRs, and SSH keys."""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from cryptography.x509.base import Certificate

from orbitlab.constants import PKI
from orbitlab.data_types import KeyUsageTypes, SSHKeyTypes
from orbitlab.manifest.pki import (
    CertificateIssued,
    CertificateIssuedWithChain,
    IntermediateCertificateManifest,
    LeafCertificateManifest,
    RootCertificateManifest,
    SecretManifest,
    SSHKeyManifest,
)
from orbitlab.services.pki import exceptions
from orbitlab.services.vault.client import SecretVault


class Certificates:
    """Manages certificate authorities, intermediate and leaf certificates, and related operations."""

    def __init__(self) -> None:
        """Initialize Certificates with manifest and vault clients, and load existing certificates."""
        self.vault = SecretVault()

    def __load_private_key__(self, pem: str) -> PrivateKeyTypes:
        """Load a private RSA key from a PEM-encoded string."""
        return serialization.load_pem_private_key(pem.encode(), password=None)

    def __load_cert__(self, pem: str) -> x509.Certificate:
        """Load an X.509 certificate from a PEM-encoded string."""
        return x509.load_pem_x509_certificate(pem.encode())

    def __generate_fingerprint__(self, pem: str) -> str:
        """Generate a SHA256 fingerprint for the given PEM data."""
        return f"SHA256:{hashlib.sha256(pem.encode()).hexdigest()}"

    def __generate_rsa_key__(self) -> rsa.RSAPrivateKey:
        """Generate a new RSA private key using the configured public exponent and key size."""
        return rsa.generate_private_key(public_exponent=PKI.RSA_PUBLIC_EXPONENT, key_size=PKI.RSA_KEY_SIZE)

    def __generate_serial__(self) -> int:
        """Generate a random 128-bit serial number for certificates."""
        return secrets.randbits(128)

    def __csr_to_pem__(self, csr: x509.CertificateSigningRequest) -> str:
        """Convert a Certificate Signing Request (CSR) to a PEM-encoded string."""
        return csr.public_bytes(serialization.Encoding.PEM).decode()

    def __key_to_pem__(self, key: rsa.RSAPrivateKey) -> str:
        """Convert a private RSA key to a PEM-encoded string."""
        return key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),  # encrypted-at-rest by Vault already
        ).decode()

    def __cert_to_pem__(self, cert: Certificate) -> str:
        """Convert a certificate object to a PEM-encoded string."""
        return cert.public_bytes(serialization.Encoding.PEM).decode()

    def create_certificate_authority(self, manifest: RootCertificateManifest) -> None:
        """Create a new root certificate authority (CA)."""
        private_key = self.__generate_rsa_key__()
        name = manifest.spec.subject.to_x509()
        now = datetime.now(UTC)
        serial_number = self.__generate_serial__()
        not_before = now - timedelta(minutes=5)
        not_after = now + timedelta(days=PKI.ROOT_CA_DAYS_VALID)

        builder = (
            x509.CertificateBuilder()
            .serial_number(serial_number)
            .subject_name(name)
            .issuer_name(name)
            .public_key(private_key.public_key())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(**KeyUsageTypes.to_x509_usage_params(manifest.spec.key_usage)), critical=True)
        )

        cert = builder.sign(private_key=private_key, algorithm=hashes.SHA256())

        key_pem = self.__key_to_pem__(private_key)
        cert_pem = self.__cert_to_pem__(cert)

        # Store private key in vault
        secret_name = Path(
            f"certificates/root/{hashlib.sha256(manifest.spec.subject.common_name.encode()).hexdigest()}",
        )
        secret_manifest = SecretManifest.store_private_key(secret_name=secret_name, key_data=key_pem)
        manifest.spec.issued = CertificateIssued(
            issuer=manifest.spec.subject.common_name,
            not_before=not_before,
            not_after=not_after,
            certificate=cert_pem,
            fingerprint=self.__generate_fingerprint__(cert_pem),
            serial_number=str(serial_number),
            secret=secret_manifest.to_ref(),
        )
        manifest.save()
        return manifest

    def create_intermediate_certificate(self, manifest: IntermediateCertificateManifest) -> None:
        """Create a new intermediate certificate signed by the specified root CA."""
        root_manifest = RootCertificateManifest.load(manifest.spec.root_ca)

        root_key = self.__load_private_key__(root_manifest.get_key())
        root_cert = self.__load_cert__(root_manifest.spec.issued.certificate)

        private_key = self.__generate_rsa_key__()
        now = datetime.now(UTC)
        serial_number = self.__generate_serial__()
        not_before = now - timedelta(minutes=5)
        not_after = now + timedelta(days=PKI.INTERMEDIATE_CA_DAYS_VALID)

        builder = (
            x509.CertificateBuilder()
            .serial_number(serial_number)
            .subject_name(manifest.spec.subject.to_x509())
            .issuer_name(root_cert.subject)
            .public_key(private_key.public_key())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(**KeyUsageTypes.to_x509_usage_params(root_manifest.spec.key_usage)),
                critical=True,
            )
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)  # pyright: ignore[reportArgumentType]
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()), critical=False)
            .add_extension(
                x509.NameConstraints(
                    permitted_subtrees=[x509.DNSName(manifest.metadata.domain_constraint)],
                    excluded_subtrees=None,
                ),
                critical=True,
            )
        )
        cert = builder.sign(private_key=root_key, algorithm=hashes.SHA256())  # pyright: ignore[reportArgumentType]

        key_pem = self.__key_to_pem__(private_key)
        cert_pem = self.__cert_to_pem__(cert)

        # Store private key in vault
        secret_name = Path(
            f"certificates/intermediate/{hashlib.sha256(manifest.spec.subject.common_name.encode()).hexdigest()}",
        )
        secret_manifest = SecretManifest.store_private_key(secret_name=secret_name, key_data=key_pem)
        manifest.spec.issued = CertificateIssuedWithChain(
            issuer=root_manifest.spec.subject.common_name,
            not_before=not_before,
            not_after=not_after,
            certificate=cert_pem,
            fingerprint=self.__generate_fingerprint__(cert_pem),
            serial_number=str(serial_number),
            secret=secret_manifest.to_ref(),
            chain=root_manifest.spec.issued.certificate,
        )
        manifest.save()
        return manifest

    def create_leaf_certificate(self, manifest: LeafCertificateManifest) -> None:
        """Create a new leaf certificate."""
        private_key = self.__generate_rsa_key__()

        key_usage = [KeyUsageTypes.DIGITAL_SIGNATURE, KeyUsageTypes.KEY_AGREEMENT]
        if manifest.spec.server_auth:
            key_usage.append(KeyUsageTypes.KEY_ENCIPHERMENT)

        builder = x509.CertificateSigningRequestBuilder().subject_name(manifest.spec.subject.to_x509())
        san = manifest.get_x509_san()
        if san:
            builder = builder.add_extension(san, critical=False)
        csr: x509.CertificateSigningRequest = builder.sign(private_key=private_key, algorithm=hashes.SHA256()) # pyright: ignore[reportArgumentType]
        cert_pem = self.sign_csr(self.__csr_to_pem__(csr), signing_ca=manifest.spec.signing_ca)
        signed_leaf = self.__load_cert__(cert_pem)

        # Store private key in vault
        secret_name = Path(
            f"certificates/leaf/{hashlib.sha256(manifest.spec.subject.common_name.encode()).hexdigest()}",
        )
        secret_manifest = SecretManifest.store_private_key(
            secret_name=secret_name, key_data=self.__key_to_pem__(private_key),
        )
        intermediate_manifest = IntermediateCertificateManifest.load(name=manifest.spec.signing_ca)
        manifest.spec.issued = CertificateIssuedWithChain(
            issuer=intermediate_manifest.spec.subject.common_name,
            not_before=signed_leaf.not_valid_before_utc,
            not_after=signed_leaf.not_valid_after_utc,
            certificate=cert_pem,
            fingerprint=self.__generate_fingerprint__(cert_pem),
            serial_number=str(signed_leaf.serial_number),
            secret=secret_manifest.to_ref(),
            chain=intermediate_manifest.spec.issued.certificate,
        )
        manifest.save()
        return manifest

    def sign_csr(self, csr_der: str, signing_ca: str) -> str:
        """Sign a Certificate Signing Request (CSR) return the cert PEM."""
        csr = x509.load_pem_x509_csr(csr_der.encode())
        intermediate_manifest = IntermediateCertificateManifest.load(name=signing_ca)
        signing_key = self.__load_private_key__(intermediate_manifest.get_key())
        signing_cert = self.__load_cert__(intermediate_manifest.spec.issued.certificate)

        now = datetime.now(UTC)
        serial_number = self.__generate_serial__()
        not_before = now - timedelta(minutes=5)
        not_after = now + timedelta(days=PKI.LEAF_CA_DAYS_VALID)

        builder = (
            x509.CertificateBuilder()
            .serial_number(serial_number)
            .subject_name(csr.subject)
            .issuer_name(signing_cert.subject)
            .public_key(csr.public_key())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        )
        for extension in csr.extensions._extensions:  # noqa: SLF001
            builder = builder.add_extension(extension.value, critical=extension.critical)

        cert = builder.sign(private_key=signing_key, algorithm=hashes.SHA256())  # pyright: ignore[reportArgumentType]
        return self.__cert_to_pem__(cert)


class SSHKey:
    """Manages SSH key pairs, including creation, storage in Vault, and manifest registration."""

    def __init__(self) -> None:
        """Initialize SSHKey with manifest and vault clients, and load existing SSH keys."""
        self.vault = SecretVault()
        self.existing_keys = SSHKeyManifest.get_existing()

    def __generate_fingerprint__(self, public_key: str) -> str:
        """Generate a SHA256 fingerprint for the given public SSH key."""
        key_body = public_key.split()[1]
        raw = base64.b64decode(key_body.encode())
        digest = base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
        return f"SHA256:{digest}"

    def get_public_key(self, name: str) -> str:
        """Retrieve the public SSH key for the given key name."""
        if name not in self.existing_keys:
            raise exceptions.SSHKeyExistsError(name=name, exists=False)
        manifest = SSHKeyManifest.load(name=name)
        return manifest.metadata.public_key

    def get_private_key(self, name: str) -> str:
        """Retrieve the private SSH key for the given key name from the vault."""
        if name not in self.existing_keys:
            raise exceptions.SSHKeyExistsError(name=name, exists=False)
        manifest = SSHKeyManifest.load(name=name)
        secret = self.vault.get(secret_name=Path(manifest.spec.secret_name), version=manifest.spec.version)
        return secret.secret_string.get_secret_value()

    def create_key_pair(self, name: str, key_type: SSHKeyTypes, passphrase: str | None = None) -> SSHKeyManifest:
        """Create a new SSH key pair and store it in the vault and manifest."""
        if name in self.existing_keys:
            raise exceptions.SSHKeyExistsError(name=name, exists=True)

        match key_type:
            case SSHKeyTypes.ED25519:
                private_key = ed25519.Ed25519PrivateKey.generate()
            case _:
                private_key = rsa.generate_private_key(
                    public_exponent=PKI.RSA_PUBLIC_EXPONENT,
                    key_size=PKI.RSA_KEY_SIZE,
                    backend=default_backend(),
                )

        encryption = (
            serialization.BestAvailableEncryption(passphrase.encode()) if passphrase else serialization.NoEncryption()
        )
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=encryption,
        ).decode()

        secret_name = Path(f"ssh/key/{key_type}/{hashlib.sha256(name.encode()).hexdigest()}")
        version = self.vault.create(secret_name=secret_name, value=private_key_pem)

        public_key = (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.OpenSSH,
                format=serialization.PublicFormat.OpenSSH,
            )
            .decode()
        )

        manifest = SSHKeyManifest.model_validate(
            {
                "name": name,
                "metadata": {
                    "public_key": public_key,
                    "fingerprint": self.__generate_fingerprint__(public_key),
                    "key_type": key_type,
                    "passphrase": bool(passphrase),
                },
                "spec": {
                    "secret_name": str(secret_name),
                    "version": version,
                },
            },
        )
        manifest.save()
        return manifest

    def delete(self, manifest: SSHKeyManifest) -> None:
        """Delete the SSH key from the vault and remove its manifest entry."""
        self.vault.delete(secret_name=Path(manifest.spec.secret_name))
        manifest.delete()
