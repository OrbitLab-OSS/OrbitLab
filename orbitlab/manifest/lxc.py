"""Schema definitions for LXC container manifests in OrbitLab."""

import secrets
import string
from ipaddress import IPv4Interface
from typing import Annotated, Self

from orbitlab.data_types import LXCState, LXCStatus, ManifestKind
from orbitlab.manifest.appliances import CustomApplianceManifest
from orbitlab.manifest.ref import Ref
from orbitlab.manifest.secrets import SecretManifest
from orbitlab.manifest.serialization import SerializeEnum, SerializeIP
from orbitlab.services.discovery import BaseApplianceManifest
from orbitlab.web.pages.compute.lxc.running.models import CreateLXCForm

from .base import BaseManifest, Metadata, Spec


class LXCMetadata(Metadata):
    """Metadata schema for LXC containers."""

    sector_name: str
    hostname: str
    on_boot: bool = True


class LXCSpec(Spec):
    """Specification schema for LXC containers."""

    status: Annotated[LXCState, SerializeEnum] = LXCState.STARTING
    node: str
    os_template: str
    disk_storage: str
    disk_size: int
    sector_id: str
    subnet_name: str
    password: Ref | None = None
    ssh_public_key: Ref | str = ""
    memory: int
    swap: int
    cores: int
    vmid: int | None = None
    address: Annotated[IPv4Interface, SerializeIP] | None = None


class LXCManifest(BaseManifest[LXCMetadata, LXCSpec]):
    """Manifest schema for LXC containers in OrbitLab."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.LXC

    def get_password(self) -> str:
        """Retrieve the current password value from the referenced secret manifest."""
        if self.spec.password:
            return SecretManifest.load(name=self.spec.password.name).get_current_value()
        return ""

    def launched(self, vmid: int, address: IPv4Interface) -> None:
        """Update the manifest to reflect that the container has been launched."""
        self.spec.vmid = vmid
        self.spec.address = address
        self.spec.status = LXCState.RUNNING
        self.save()

    def set_status(self, status: LXCStatus) -> None:
        """Update the container status in the manifest based on the provided LXCStatus."""
        match status:
            case LXCStatus.START:
                self.spec.status = LXCState.RUNNING
            case LXCStatus.REBOOT:
                self.spec.status = LXCState.RUNNING
            case LXCStatus.STOP:
                self.spec.status = LXCState.STOPPED
            case LXCStatus.SHUTDOWN:
                self.spec.status = LXCState.STOPPED
        self.save()

    @classmethod
    def _generate_id(cls) -> str:
        existing = cls.get_existing()
        prefix = "lxc-"
        lxc_id = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))
        while prefix + lxc_id in existing:
            lxc_id = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))
        return prefix + lxc_id

    @classmethod
    def create(cls, form: CreateLXCForm) -> Self:
        """Create a new LXCManifest instance from the provided form data."""
        if form.appliance in BaseApplianceManifest.get_existing():
            appliance = BaseApplianceManifest.load(name=form.appliance)
        else:
            appliance = CustomApplianceManifest.load(name=form.appliance)
        lxc_id = cls._generate_id()
        password = SecretManifest.create_lxc_password(lxc_id=lxc_id, password=form.password)
        manifest = cls(
            name=lxc_id,
            metadata=LXCMetadata(
                sector_name=form.sector,
                hostname=form.name,
            ),
            spec=LXCSpec(
                node=form.node,
                os_template=appliance.ostemplate,
                disk_storage=form.rootfs,
                disk_size=form.disk_size,
                sector_id=form.sector,
                subnet_name=form.subnet,
                memory=form.memory,
                swap=form.swap,
                cores=form.cores,
                password=password.to_ref(),
            ),
        )
        manifest.save()
        return manifest
