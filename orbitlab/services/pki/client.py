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
from cryptography.x509.base import Certificate
from cryptography.x509.oid import NameOID

import orbitlab.manifest.schemas.secrets as schemas
from orbitlab.constants import PKI
from orbitlab.data_types import CertificateTypes, CSRStatus, KeyUsageTypes, ManifestKind, SSHKeyTypes
from orbitlab.manifest.client import ManifestClient
from orbitlab.services.pki import exceptions
from orbitlab.services.pki.models import IntermediateCA, LeafCertificate, Subject
from orbitlab.services.vault.client import SecretVault


class Certificates:
    """Manages certificate authorities, intermediate and leaf certificates, and related operations.

    This class provides methods for creating, signing, and managing X.509 certificates and CSRs,
    as well as storing and retrieving certificate data from manifests and a secret vault.
    """

    def __init__(self) -> None:
        """Initialize Certificates with manifest and vault clients, and load existing certificates."""
        self.manifest = ManifestClient()
        self.vault = SecretVault()
        self.existing_certificates = self.manifest.get_existing_by_kind(kind=ManifestKind.CERTIFICATE)
        self.existing_csrs = self.manifest.get_existing_by_kind(kind=ManifestKind.CSR)

    def __load_private_key__(self, pem: str) -> rsa.RSAPrivateKey:
        """Load a private RSA key from a PEM-encoded string."""
        return serialization.load_pem_private_key(pem.encode(), password=None)

    def __load_cert__(self, pem: str) -> x509.Certificate:
        """Load an X.509 certificate from a PEM-encoded string."""
        return x509.load_pem_x509_certificate(pem.encode())

    def __load_csr__(self, pem: str) -> x509.CertificateSigningRequest:
        """Load a Certificate Signing Request (CSR) from a PEM-encoded string."""
        return x509.load_pem_x509_csr(pem.encode())

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

    def __get_common_name__(self, csr: x509.CertificateSigningRequest) -> str | None:
        """Extract the common name (CN) from a certificate signing request (CSR)."""
        common_name = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if not common_name:
            return None
        common_name = common_name[0].value
        if isinstance(common_name, bytes):
            common_name = common_name.decode()
        return common_name

    def __get_signing_cert__(self, intermediate_ca: str) -> schemas.CertificateManifest:
        """Retrieve the manifest for the specified intermediate CA, ensuring it exists and is of the correct type."""
        if intermediate_ca not in self.existing_certificates:
            raise exceptions.CertificateExistsError(name=intermediate_ca, exists=False)

        intermediate_manifest = self.manifest.load(
            name=intermediate_ca,
            kind=ManifestKind.CERTIFICATE,
            model=schemas.CertificateManifest,
        )
        if intermediate_manifest.metadata.type != CertificateTypes.INTERMEDIATE:
            raise exceptions.CertificateTypeError(
                common_name=intermediate_ca,
                cert_type=CertificateTypes.INTERMEDIATE,
            )
        return intermediate_manifest

    def __verify_csr_signing_request__(
        self,
        manifest: schemas.CSRManifest,
        csr: x509.CertificateSigningRequest,
    ) -> schemas.CSRManifest:
        """Verify the status and fingerprint of a CSR signing request and update its status if necessary."""
        if manifest.spec.status == CSRStatus.PENDING:
            if manifest.spec.submitted_at < (datetime.now(UTC) - timedelta(days=30)):
                manifest.spec.status = CSRStatus.REJECTED
                manifest.spec.rejected_reason = "Request older than 30 days. Submit a new request."
            elif manifest.spec.csr_fingerprint != self.__generate_fingerprint__(self.__csr_to_pem__(csr)):
                manifest.spec.status = CSRStatus.REJECTED
                manifest.spec.rejected_reason = "CSR fingerprint does not match previous request."
        return manifest

    def create_certificate_authority(
        self,
        subject: Subject,
        key_usage: list[KeyUsageTypes],
    ) -> schemas.CertificateManifest:
        """Create a new certificate authority (CA) with the given subject and key usage.

        Args:
            subject (Subject): The subject information for the CA certificate.
            key_usage (list[KeyUsageTypes]): List of key usage types for the CA.

        Returns:
            CertificateManifest: The manifest object representing the created CA certificate.

        Raises:
            CertificateExistsError: If a certificate with the given subject already exists.
        """
        if subject.common_name in self.existing_certificates:
            raise exceptions.CertificateExistsError(name=subject.common_name, exists=True)

        private_key = self.__generate_rsa_key__()
        name = subject.to_x509()
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
            .add_extension(x509.KeyUsage(**KeyUsageTypes.to_x509_usage_params(key_usage)), critical=True)
        )

        cert = builder.sign(private_key=private_key, algorithm=hashes.SHA256())

        key_pem = self.__key_to_pem__(private_key)
        cert_pem = self.__cert_to_pem__(cert)

        # Store private key in vault
        secret_name = Path(
            f"certificates/{CertificateTypes.ROOT}/{hashlib.sha256(subject.common_name.encode()).hexdigest()}",
        )
        version = self.vault.create(secret_name=secret_name, value=key_pem)

        manifest = schemas.CertificateManifest(
            name=subject.common_name,
            metadata=schemas.CertificateMetadata(
                type=CertificateTypes.ROOT,
                common_name=subject.common_name,
                issuer=subject.common_name,
                org=subject.org,
                org_unit=subject.org_unit,
                country=subject.country,
                state_or_province=subject.state_or_province,
                locality=subject.locality,
                not_before=not_before,
                not_after=not_after,
                fingerprint=self.__generate_fingerprint__(cert_pem),
                serial_number=serial_number,
                certificate=cert_pem,
                key_usage=key_usage,
            ),
            spec=schemas.SecretSpec(
                secret_name=str(secret_name),
                version=version,
            ),
        )
        self.manifest.save(manifest=manifest)
        return manifest

    def create_intermediate_certificate(self, intermediate_ca: IntermediateCA) -> schemas.CertificateManifest:
        """Create a new intermediate certificate signed by the specified root CA.

        Args:
            intermediate_ca (IntermediateCA): The intermediate certificate configuration.

        Returns:
            CertificateManifest: The manifest object representing the created intermediate certificate.

        Raises:
            CertificateExistsError: If the `common_name` already exists or the `root_ca` does not exist.
        """
        if intermediate_ca.common_name in self.existing_certificates:
            raise exceptions.CertificateExistsError(name=intermediate_ca.common_name, exists=True)
        if intermediate_ca.root_ca not in self.existing_certificates:
            raise exceptions.CertificateExistsError(name=intermediate_ca.root_ca, exists=False)

        root_manifest = self.manifest.load(
            name=intermediate_ca.root_ca,
            kind=ManifestKind.CERTIFICATE,
            model=schemas.CertificateManifest,
        )
        if root_manifest.metadata.type != CertificateTypes.ROOT:
            raise exceptions.CertificateTypeError(common_name=intermediate_ca.root_ca, cert_type=CertificateTypes.ROOT)

        root_private_key = self.vault.get(
            secret_name=root_manifest.spec.secret_name,
            version=root_manifest.spec.version,
        )

        root_key = self.__load_private_key__(root_private_key.secret_string.get_secret_value())
        root_cert = self.__load_cert__(root_manifest.metadata.certificate)

        private_key = self.__generate_rsa_key__()
        now = datetime.now(UTC)
        serial_number = self.__generate_serial__()
        not_before = now - timedelta(minutes=5)
        not_after = now + timedelta(days=PKI.INTERMEDIATE_CA_DAYS_VALID)

        subject = Subject(
            common_name=intermediate_ca.common_name,
            org=root_manifest.metadata.org,
            org_unit=root_manifest.metadata.org_unit,
            country=root_manifest.metadata.country,
            state_or_province=root_manifest.metadata.state_or_province,
            locality=root_manifest.metadata.locality,
        )

        builder = (
            x509.CertificateBuilder()
            .serial_number(serial_number)
            .subject_name(subject.to_x509())
            .issuer_name(root_cert.subject)
            .public_key(private_key.public_key())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(**KeyUsageTypes.to_x509_usage_params(root_manifest.metadata.key_usage)),
                critical=True,
            )
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()), critical=False)
            .add_extension(
                x509.NameConstraints(
                    permitted_subtrees=[x509.DNSName(intermediate_ca.domain_constraint)],
                    excluded_subtrees=None,
                ),
                critical=True,
            )
        )
        cert = builder.sign(private_key=root_key, algorithm=hashes.SHA256())

        key_pem = self.__key_to_pem__(private_key)
        cert_pem = self.__cert_to_pem__(cert)

        # Store private key in vault
        secret_name = Path(
            f"certificates/{CertificateTypes.INTERMEDIATE}/{hashlib.sha256(subject.common_name.encode()).hexdigest()}",
        )
        version = self.vault.create(secret_name=secret_name, value=key_pem)

        manifest =schemas. CertificateManifest(
            name=subject.common_name,
            metadata=schemas.CertificateMetadata(
                type=CertificateTypes.INTERMEDIATE,
                common_name=subject.common_name,
                issuer=root_manifest.metadata.common_name,
                org=subject.org,
                org_unit=subject.org_unit,
                country=subject.country,
                state_or_province=subject.state_or_province,
                locality=subject.locality,
                not_before=not_before,
                not_after=not_after,
                fingerprint=self.__generate_fingerprint__(cert_pem),
                serial_number=serial_number,
                certificate=cert_pem,
                key_usage=root_manifest.metadata.key_usage,
                domain_constraint=intermediate_ca.domain_constraint,
            ),
            spec=schemas.SecretSpec(
                secret_name=str(secret_name),
                version=version,
            ),
        )
        self.manifest.save(manifest=manifest)
        return manifest

    def create_leaf_certificate(self, leaf_certificate: LeafCertificate) -> schemas.CertificateManifest:
        """Create a new leaf certificate.

        Generates a private key and CSR, signs the CSR, and stores the certificate and key. Then deletes the CSR.

        Args:
            leaf_certificate (LeafCertificate): The leaf certificate configuration.

        Returns:
            CertificateManifest: The manifest object representing the created leaf certificate.

        Raises:
            CertificateExistsError: If a certificate with the given common name already exists.
        """
        if leaf_certificate.common_name in self.existing_certificates:
            raise exceptions.CertificateExistsError(name=leaf_certificate.common_name, exists=True)

        private_key = self.__generate_rsa_key__()
        csr_der = self.create_csr(self.__key_to_pem__(private_key), leaf_certificate)
        self.existing_csrs = self.manifest.get_existing_by_kind(ManifestKind.CSR) # Reload CSRs
        csr_manifest = self.sign_csr(csr_der)

        # Store private key in vault
        secret_name = Path(
            f"certificates/{CertificateTypes.INTERMEDIATE}/{hashlib.sha256(leaf_certificate.common_name.encode()).hexdigest()}",
        )
        version = self.vault.create(secret_name=secret_name, value=self.__key_to_pem__(private_key))

        manifest = schemas.CertificateManifest(
            name=csr_manifest.name,
            metadata=schemas.CertificateMetadata(
                type=CertificateTypes.LEAF,
                common_name=csr_manifest.name,
                issuer=csr_manifest.metadata.issuer,
                org=csr_manifest.metadata.org,
                org_unit=csr_manifest.metadata.org_unit,
                country=csr_manifest.metadata.country,
                state_or_province=csr_manifest.metadata.state_or_province,
                locality=csr_manifest.metadata.locality,
                not_before=csr_manifest.metadata.not_before,
                not_after=csr_manifest.metadata.not_after,
                certificate=csr_manifest.metadata.certificate,
                fingerprint=csr_manifest.metadata.fingerprint,
                key_usage=csr_manifest.metadata.key_usage,
                serial_number=csr_manifest.metadata.serial_number,
                san_dns=csr_manifest.metadata.san_dns,
                san_ips=csr_manifest.metadata.san_ips,
                chain=csr_manifest.metadata.chain,
            ),
            spec=schemas.SecretSpec(
                secret_name=str(secret_name),
                version=version,
            ),
        )

        self.manifest.save(manifest=manifest)
        self.delete_csr(manifest=csr_manifest)
        return manifest

    def create_csr(self, key: str, lc: LeafCertificate) -> str:
        """
        Create a Certificate Signing Request (CSR) for a given leaf certificate and private key.

        Args:
            key (str): The PEM-encoded private key as a string.
            lc (LeafCertificate): The leaf certificate information.

        Returns:
            str: The DER-encoded CSR as a string.

        Raises:
            CSRExistsError: If a CSR with the given common name already exists.
        """
        if lc.common_name in self.existing_csrs:
            raise exceptions.CSRExistsError(name=lc.common_name, exists=True)

        private_key = self.__load_private_key__(key)
        intermediate_manifest = self.__get_signing_cert__(intermediate_ca=lc.intermediate_ca)

        subject = Subject(
            common_name=lc.common_name,
            org=intermediate_manifest.metadata.org,
            org_unit=intermediate_manifest.metadata.org_unit,
            country=intermediate_manifest.metadata.country,
            state_or_province=intermediate_manifest.metadata.state_or_province,
            locality=intermediate_manifest.metadata.locality,
        )

        key_usage = [KeyUsageTypes.DIGITAL_SIGNATURE, KeyUsageTypes.KEY_AGREEMENT]
        if lc.server_auth:
            key_usage.append(KeyUsageTypes.KEY_ENCIPHERMENT)

        builder = x509.CertificateSigningRequestBuilder().subject_name(subject.to_x509())
        san = lc.get_x509_san()
        if san:
            builder = builder.add_extension(san, critical=False)
        csr = builder.sign(private_key, hashes.SHA256())

        manifest = schemas.CSRManifest(
            name=lc.common_name,
            metadata=schemas.CSRMetadata(
                common_name=subject.common_name,
                issuer=intermediate_manifest.metadata.common_name,
                org=subject.org,
                org_unit=subject.org_unit,
                country=subject.country,
                state_or_province=subject.state_or_province,
                locality=subject.locality,
                san_dns=lc.san_dns,
                san_ips=lc.san_ips,
                key_usage=key_usage,
            ),
            spec=schemas.CSRSpec(
                key_fingerprint=self.__generate_fingerprint__(self.__key_to_pem__(private_key)),
                csr_fingerprint=self.__generate_fingerprint__(self.__csr_to_pem__(csr)),
                submitted_at=datetime.now(UTC),
                status=CSRStatus.PENDING,
            ),
        )
        self.manifest.save(manifest=manifest)
        return self.__csr_to_pem__(csr)

    def sign_csr(self, csr_der: str) -> schemas.CSRManifest:
        """
        Sign a Certificate Signing Request (CSR) and update its manifest status.

        Args:
            csr_der (str): The DER-encoded CSR as a string.

        Returns:
            CSRManifest: The updated manifest object for the signed CSR.

        Raises:
            CSRSigningError: If the CSR does not contain a Common Name.
            CSRExistsError: If the CSR with the given Common Name does not exist.
        """
        csr = self.__load_csr__(csr_der)
        common_name = self.__get_common_name__(csr=csr)

        if not common_name:
            raise exceptions.CSRSigningError(msg="Common Name not found in CSR.")

        if common_name not in self.existing_csrs:
            raise exceptions.CSRExistsError(name=common_name, exists=False)

        csr_manifest = self.manifest.load(name=common_name, kind=ManifestKind.CSR, model=schemas.CSRManifest)
        csr_manifest = self.__verify_csr_signing_request__(manifest=csr_manifest, csr=csr)
        if csr_manifest.spec.status != CSRStatus.PENDING:
            return csr_manifest

        intermediate_manifest = self.__get_signing_cert__(intermediate_ca=csr_manifest.metadata.issuer)
        signing_private_key = self.vault.get(
            secret_name=intermediate_manifest.spec.secret_name,
            version=intermediate_manifest.spec.version,
        )

        signing_key = self.__load_private_key__(signing_private_key.secret_string.get_secret_value())
        signing_cert = self.__load_cert__(intermediate_manifest.metadata.certificate)

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

        cert = builder.sign(private_key=signing_key, algorithm=hashes.SHA256())
        cert_pem = self.__cert_to_pem__(cert)

        csr_manifest.metadata.serial_number = serial_number
        csr_manifest.metadata.not_before = not_before
        csr_manifest.metadata.not_after = not_after
        csr_manifest.metadata.fingerprint = self.__generate_fingerprint__(cert_pem)
        csr_manifest.metadata.chain = intermediate_manifest.metadata.certificate
        csr_manifest.metadata.certificate = cert_pem
        csr_manifest.spec.signed_at = now
        csr_manifest.spec.status = CSRStatus.ISSUED

        self.manifest.save(csr_manifest)
        return csr_manifest

    def delete_csr(self, manifest: schemas.CSRManifest) -> None:
        """Delete a Certificate Signing Request (CSR) manifest entry.

        Args:
            manifest (CSRManifest): The manifest object representing the CSR to delete.
        """
        self.manifest.delete(manifest=manifest)


class SSHKey:
    """Manages SSH key pairs, including creation, storage in Vault, and manifest registration."""

    def __init__(self) -> None:
        """Initialize SSHKey with manifest and vault clients, and load existing SSH keys."""
        self.manifest = ManifestClient()
        self.vault = SecretVault()
        self.existing_keys = self.manifest.get_existing_by_kind(kind=ManifestKind.SSH_KEY)

    def __generate_fingerprint__(self, public_key: str) -> str:
        """Generate a SHA256 fingerprint for the given public SSH key."""
        key_body = public_key.split()[1]
        raw = base64.b64decode(key_body.encode())
        digest = base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
        return f"SHA256:{digest}"

    def get_public_key(self, name: str) -> str:
        """Retrieve the public SSH key for the given key name.

        Args:
            name (str): The name of the SSH key.

        Returns:
            str: The public key as a string.

        Raises:
            SSHKeyExistsError: If the key with the given name does not exist.
        """
        if name not in self.existing_keys:
            raise exceptions.SSHKeyExistsError(name=name, exists=False)
        manifest = self.manifest.load(name=name, kind=ManifestKind.SSH_KEY, model=schemas.SSHKeyManifest)
        return manifest.metadata.public_key

    def get_private_key(self, name: str) -> str:
        """Retrieve the private SSH key for the given key name from the vault.

        Args:
            name (str): The name of the SSH key.

        Returns:
            str: The private key as a string.

        Raises:
            SSHKeyExistsError: If the key with the given name does not exist.
        """
        if name not in self.existing_keys:
            raise exceptions.SSHKeyExistsError(name=name, exists=False)
        manifest = self.manifest.load(name=name, kind=ManifestKind.SSH_KEY, model=schemas.SSHKeyManifest)
        secret = self.vault.get(secret_name=Path(manifest.spec.secret_name), version=manifest.spec.version)
        return secret.secret_string.get_secret_value()

    def create_key_pair(
        self,
        name: str,
        key_type: SSHKeyTypes,
        passphrase: str | None = None,
    ) -> schemas.SSHKeyManifest:
        """Create a new SSH key pair and store it in the vault and manifest.

        Args:
            name (str): The name of the SSH key.
            key_type (SSHKeyTypes): The type of SSH key to generate (e.g., ED25519, RSA).
            passphrase (str | None, optional): Passphrase to encrypt the private key, or None for no encryption.

        Returns:
            SSHKeyManifest: The manifest object representing the created SSH key.

        Raises:
            SSHKeyExistsError: If a key with the given name already exists.
        """
        if name in self.existing_keys:
            raise exceptions.SSHKeyExistsError(name=name, exists=True)

        match (key_type):
            case SSHKeyTypes.ED25519:
                private_key = ed25519.Ed25519PrivateKey.generate()
            case _:
                private_key = rsa.generate_private_key(
                    public_exponent=PKI.RSA_PUBLIC_EXPONENT,
                    key_size=PKI.RSA_KEY_SIZE,
                    backend=default_backend(),
                )

        encryption = (
            serialization.BestAvailableEncryption(passphrase.encode())
            if passphrase else
            serialization.NoEncryption()
        )
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=encryption,
        ).decode()

        secret_name = Path(f"ssh/key/{key_type}/{hashlib.sha256(name.encode()).hexdigest()}")
        version = self.vault.create(secret_name=secret_name, value=private_key_pem)

        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        ).decode()

        manifest = schemas.SSHKeyManifest(
            name=name,
            metadata=schemas.SSHKeyMetadata(
                public_key=public_key,
                fingerprint=self.__generate_fingerprint__(public_key),
                key_type=key_type,
                passphrase=bool(passphrase),
            ),
            spec=schemas.SecretSpec(
                secret_name=str(secret_name),
                version=version,
            ),
        )
        self.manifest.save(manifest)
        return manifest

    def delete(self, manifest: schemas.SSHKeyManifest) -> None:
        """Delete the SSH key from the vault and remove its manifest entry.

        Args:
            manifest (SSHKeyManifest): The manifest object representing the SSH key to delete.
        """
        self.vault.delete(secret_name=Path(manifest.spec.secret_name))
        self.manifest.delete(manifest=manifest)
