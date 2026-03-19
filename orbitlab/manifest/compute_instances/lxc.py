"""Schema definitions for LXC container manifests in OrbitLab."""

from typing import TYPE_CHECKING, Annotated, Self

from orbitlab.data_types import ManifestKind
from orbitlab.manifest.base import BaseManifest, Metadata, Spec
from orbitlab.manifest.compute_templates import CustomApplianceManifest
from orbitlab.manifest.ref import Ref
from orbitlab.manifest.secrets import SecretManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.manifest.serialization import SerializeEnum
from orbitlab.services.discovery import BaseApplianceManifest

if TYPE_CHECKING:
    from orbitlab.web.pages.compute.lxc.instances.models import CreateLXCForm


class LXCMetadata(Metadata):
    """Metadata schema for LXC containers."""

    sector_name: str
    hostname: str
    on_boot: bool = True
    node: str
    vmid: int = 0


class LXCSpec(Spec):
    """Specification schema for LXC containers."""

    os_template: str
    disk_storage: str
    disk_size: int
    sector: str
    password: Ref
    ssh_public_key: Ref | str = ""
    memory: int
    swap: int
    cores: int


class LXCManifest(BaseManifest[LXCMetadata, LXCSpec]):
    """Manifest schema for LXC containers in OrbitLab."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.LXC

    def create_lxc_params(self, vmid: int) -> dict[str, int | str]:
        """Generate the parameters required to create an LXc in Proxmox."""
        self.metadata.vmid = vmid
        dns_address = SectorManifest.load(name=self.spec.sector).dns_address
        self.save()
        return {
            "features": "nesting=1",
            "ostemplate": self.spec.os_template,
            "hostname": self.metadata.hostname,
            "cores": self.spec.cores,
            "memory": self.spec.memory * 1024,
            "swap": self.spec.memory * 1024,
            "net0": f"name=eth0,bridge={self.spec.sector},ip=dhcp,mtu=1450",
            "rootfs": f"{self.spec.disk_storage}:{self.spec.disk_size}",
            "unprivileged": "1",
            "vmid": vmid,
            "ssh-public-keys": "",
            "password": self.get_password(),
            "searchdomain": "sector.internal",
            "nameserver": f"{dns_address.ip}",
            "onboot": "1" if self.metadata.on_boot else "0",
        }

    def get_password(self) -> str:
        """Retrieve the current password value from the referenced secret manifest."""
        if self.spec.password:
            return SecretManifest.load(name=self.spec.password.name).get_current_value()
        return ""

    def delete(self) -> None:
        """Delete the VM manifest and remove its associated secret."""
        if self.spec.password:
            SecretManifest.load(name=self.spec.password.name).delete()
        super().delete()

    @classmethod
    def create(cls, form_data: "CreateLXCForm") -> Self:
        """Create a new LXCManifest instance from the provided form data."""
        if form_data.appliance in BaseApplianceManifest.get_existing():
            appliance = BaseApplianceManifest.load(name=form_data.appliance)
        else:
            appliance = CustomApplianceManifest.load(name=form_data.appliance)
        lxc_id = cls._generate_id(prefix="lxc")
        password = SecretManifest.create_lxc_password(lxc_id=lxc_id, password=form_data.password)
        manifest = cls(
            name=lxc_id,
            metadata=LXCMetadata(
                sector_name=SectorManifest.load(name=form_data.sector).spec.alias,
                hostname=form_data.name,
                node=form_data.node,
            ),
            spec=LXCSpec(
                os_template=appliance.spec.volume_id,
                disk_storage=form_data.rootfs,
                disk_size=form_data.disk_size,
                sector=form_data.sector,
                memory=form_data.memory,
                swap=form_data.swap,
                cores=form_data.cores,
                password=password.to_ref(),
            ),
        )
        manifest.save()
        return manifest
