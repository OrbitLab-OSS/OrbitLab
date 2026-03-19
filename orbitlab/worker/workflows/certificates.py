"""PKI Workflows."""

import reflex as rx

from orbitlab.manifest.pki import IntermediateCertificateManifest, LeafCertificateManifest, RootCertificateManifest
from orbitlab.web.pages.secrets_pki.pki.states import (
    IntermediateCertificatesState,
    LeafCertificatesState,
    RootCertificatesState,
)
from orbitlab.worker.workflows.utilities import PKIUtils

from .base import Workflow, WorkflowPayload


class PKIPayload(WorkflowPayload):
    """Default payload for PKI workflows."""

    manifest: str
    rotate: bool = False


class CreateRootCertificateAuthorityV1(Workflow, PKIUtils):
    """Workflow for changing the state of an LXC container."""

    TYPE: str = "pki.create-root"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[PKIPayload] = PKIPayload
    payload: PKIPayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        if self.payload.manifest not in RootCertificateManifest.get_existing():
            await self.fail(f"Manifest for {self.payload.manifest} does not exist")
            return
        manifest = RootCertificateManifest.load(name=self.payload.manifest)
        if manifest.spec.issued and not self.payload.rotate:
            await self.succeed(f"Certificate {self.payload.manifest} already issued.")

    async def provision(self) -> None:
        """Download the appliance."""
        manifest = RootCertificateManifest.load(name=self.payload.manifest)
        await self.create_root(manifest=manifest)
        return await self.succeed(f"Certificate {self.payload.manifest} created.")

    async def on_succeed(self) -> None:
        """Emit reflex events to notify of success."""
        manifest = RootCertificateManifest.load(name=self.payload.manifest)
        message = f"Root CA {manifest.spec.subject.common_name} issued."
        if self.payload.rotate:
            message = f"Root CA {manifest.spec.subject.common_name} rotated."
        await self.emit_reflex_events(
            events=[RootCertificatesState.cache_clear("all"), rx.toast.success(message=message)],
        )

    async def on_failure(self) -> None:
        """Delete manifest if it exists and we're not updating."""
        if self.payload.manifest in RootCertificateManifest.get_existing() and not self.payload.rotate:
            RootCertificateManifest.load(name=self.payload.manifest).delete()
            await self.emit_reflex_events(events=[RootCertificatesState.cache_clear("all")])


class CreateIntermediateCertificateAuthorityV1(Workflow, PKIUtils):
    """Workflow for changing the state of an LXC container."""

    TYPE: str = "pki.create-intermediate"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[PKIPayload] = PKIPayload
    payload: PKIPayload

    async def validate(self) -> PKIPayload:
        """Validate if appliance already exists and handle accordingly."""
        if self.payload.manifest not in IntermediateCertificateManifest.get_existing():
            await self.fail(f"Manifest for {self.payload.manifest} does not exist")
            return
        manifest = IntermediateCertificateManifest.load(name=self.payload.manifest)
        if manifest.spec.issued and not self.payload.rotate:
            await self.succeed(f"Certificate {self.payload.manifest} already issued.")

    async def provision(self) -> None:
        """Create the intermediate certificate authority."""
        manifest = IntermediateCertificateManifest.load(name=self.payload.manifest)
        await self.create_intermediate(manifest=manifest)
        await self.succeed(f"Certificate {self.payload.manifest} issued.")

    async def on_succeed(self) -> None:
        """Emit reflex events to notify of success."""
        manifest = IntermediateCertificateManifest.load(name=self.payload.manifest)
        message = f"Root CA {manifest.spec.subject.common_name} issued."
        if self.payload.rotate:
            message = f"Root CA {manifest.spec.subject.common_name} rotated."
        await self.emit_reflex_events(
            events=[
                IntermediateCertificatesState.cache_clear("all"),
                rx.toast.success(message=message),
            ],
        )

    async def on_failure(self) -> None:
        """Delete manifest if it exists and we're not updating."""
        if self.payload.manifest in IntermediateCertificateManifest.get_existing() and not self.payload.rotate:
            IntermediateCertificateManifest.load(name=self.payload.manifest).delete()


class CreateLeafCertificateV1(Workflow, PKIUtils):
    """Workflow for changing the state of an LXC container."""

    TYPE: str = "pki.create-leaf"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[PKIPayload] = PKIPayload
    payload: PKIPayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        if self.payload.manifest not in LeafCertificateManifest.get_existing():
            await self.fail(f"Manifest for {self.payload.manifest} does not exist")
            return
        manifest = LeafCertificateManifest.load(name=self.payload.manifest)
        if manifest.spec.issued and not self.payload.rotate:
            await self.succeed(f"Certificate {self.payload.manifest} already issued.")

    async def provision(self) -> None:
        """Create the leaf certificate."""
        manifest = LeafCertificateManifest.load(name=self.payload.manifest)
        await self.create_leaf(manifest=manifest)
        await self.succeed(f"Certificate {self.payload.manifest} issued.")

    async def on_succeed(self) -> None:
        """Emit reflex events to notify of success."""
        manifest = LeafCertificateManifest.load(name=self.payload.manifest)
        message = f"Root CA {manifest.spec.subject.common_name} issued."
        if self.payload.rotate:
            message = f"Root CA {manifest.spec.subject.common_name} rotated."
        await self.emit_reflex_events(
            events=[
                LeafCertificatesState.cache_clear("all"),
                rx.toast.success(message=message),
            ],
        )

    async def on_failure(self) -> None:
        """Delete manifest if it exists and we're not updating."""
        if self.payload.manifest in LeafCertificateManifest.get_existing() and not self.payload.rotate:
            LeafCertificateManifest.load(name=self.payload.manifest).delete()


class DeleteCertificateV1(Workflow, PKIUtils):
    """Workflow to delete a certificate."""

    TYPE: str = "pki.delete"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[PKIPayload] = PKIPayload
    payload: PKIPayload

    async def validate(self) -> None:
        """Ensure the manifest exists."""
        if self.payload.manifest in LeafCertificateManifest.get_existing():
            self.succeed(f"Manifest {self.payload.manifest} does not exist or already deleted.")
        if self.payload.manifest in IntermediateCertificateManifest.get_existing():
            self.succeed(f"Manifest {self.payload.manifest} does not exist or already deleted.")
        if self.payload.manifest in RootCertificateManifest.get_existing():
            self.succeed(f"Manifest {self.payload.manifest} does not exist or already deleted.")

    async def provision(self) -> None:
        """Delete the certificate manifest."""
        if self.payload.manifest in LeafCertificateManifest.get_existing():
            LeafCertificateManifest.load(self.payload.manifest).delete()
            events = [LeafCertificatesState.cache_clear("all")]
        if self.payload.manifest in IntermediateCertificateManifest.get_existing():
            IntermediateCertificateManifest.load(self.payload.manifest).delete()
            events = [IntermediateCertificatesState.cache_clear("all")]
        if self.payload.manifest in RootCertificateManifest.get_existing():
            RootCertificateManifest.load(self.payload.manifest).delete()
            events = [RootCertificatesState.cache_clear("all")]

        await self.emit_reflex_events(events=events)
        await self.succeed(f"Certificate {self.payload.manifest} deleted.")
