"""DataCore Manifests."""

from ipaddress import IPv4Interface
from typing import TYPE_CHECKING, Annotated, Self

from pydantic import BaseModel, Field

from orbitlab.data_types import ManifestKind
from orbitlab.manifest.secrets import SecretManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.services import SecretVault

from .base import BaseManifest, Metadata, Ref, Spec
from .serialization import SerializeEnum, SerializeIP

if TYPE_CHECKING:
    from orbitlab.web.pages.datacore.models import CreateDataCoreForm


class DataCoreNode(BaseModel):
    """Represents a DataCore cluster node with VM ID and name."""

    vmid: int
    name: str


class DataCoreMetadata(Metadata):
    """Metadata for DataCore cluster configuration."""

    name: str
    sector_alias: str
    nodes: list[DataCoreNode] = Field(default_factory=list)


class DataCoreSpec(Spec):
    """DataCore specification for cluster configuration and VM parameters."""

    rw_virtual_router_id: int = Field(ge=1, le=255)
    ro_virtual_router_id: int = Field(ge=1, le=255)
    rw_vip: Annotated[IPv4Interface, SerializeIP]
    ro_vip: Annotated[IPv4Interface, SerializeIP]
    replicas: int
    superuser_password: Ref
    replication_password: Ref
    memory_gb: int
    cores: int
    capacity_gb: int
    storage: str
    sector: str
    application_user: str
    application_password: Ref
    application_database: str


class DataCoreManifest(BaseManifest[DataCoreMetadata, DataCoreSpec]):
    """DataCore cluster manifest for storage configuration."""

    kind: Annotated[ManifestKind, SerializeEnum] = ManifestKind.DATA_CORE

    def generate_cluster_config(self) -> dict[str, str | int]:
        """Generate DataCore cluster configuration with VIP and authentication details."""
        return {
            "rw_virtual_router_id": self.spec.rw_virtual_router_id,
            "ro_virtual_router_id": self.spec.ro_virtual_router_id,
            "rw_vip": str(self.spec.rw_vip),
            "ro_vip": str(self.spec.ro_vip),
            "keepalived_password": SecretVault.generate_random_password(),
            "superuser_password": SecretManifest.load(name=self.spec.superuser_password.name).get_current_value(),
            "replication_password": SecretManifest.load(name=self.spec.replication_password.name).get_current_value(),
            "application_user": self.spec.application_user,
            "application_password": SecretManifest.load(name=self.spec.application_password.name).get_current_value(),
            "application_database": self.spec.application_database,
        }

    def generate_node_params(self, vmid: int, volume_id: str) -> dict[str, str]:
        """Generate node parameters for DataCore VM creation."""
        name = self._generate_id(prefix=self.name, count=6, skip_check=True)
        self.metadata.nodes.append(DataCoreNode(vmid=vmid, name=name))
        self.save()
        sector = SectorManifest.load(name=self.spec.sector)
        return {
            "features": "nesting=1",
            "ostemplate": volume_id,
            "hostname": name,
            "cores": self.spec.cores,
            "memory": self.spec.memory_gb * 1024,
            "swap": 512,
            "net0": f"name=eth0,bridge={self.spec.sector},ip=dhcp,mtu=1450",
            "rootfs": f"{self.spec.storage}:{self.spec.capacity_gb}",
            "unprivileged": "1",
            "vmid": vmid,
            "ssh-public-keys": "",
            "password": SecretVault.generate_random_password(),
            "searchdomain": "sector.internal",
            "nameserver": f"{sector.dns_address.ip}",
            "onboot": "1",
        }

    def remove_node(self, name: str) -> None:
        """Remove a DataCore node from the cluster by name."""
        node = next(iter([_node for _node in self.metadata.nodes if _node.name == name]))
        self.metadata.nodes.remove(node)
        self.save()

    def delete(self) -> None:
        """Delete the DataCore manifest and all associated secrets."""
        sector = SectorManifest.load(name=self.spec.sector)
        sector.release_vip(vrid=self.spec.rw_virtual_router_id)
        sector.release_vip(vrid=self.spec.ro_virtual_router_id)
        SecretManifest.load(name=self.spec.superuser_password.name).delete()
        SecretManifest.load(name=self.spec.replication_password.name).delete()
        SecretManifest.load(name=self.spec.application_password.name).delete()
        return super().delete()

    @classmethod
    def create(cls, form_data: "CreateDataCoreForm") -> Self:
        """Create a new DataCore manifest from form data."""
        datacore_name = cls._generate_id(prefix="datacore", count=8)
        sector = SectorManifest.load(name=form_data.sector)
        leader_sector_vip = sector.assign_vip()
        replica_sector_vip = sector.assign_vip()
        manifest = cls(
            name=datacore_name,
            metadata=DataCoreMetadata(name=form_data.name, sector_alias=sector.spec.alias),
            spec=DataCoreSpec(
                rw_virtual_router_id=leader_sector_vip.virtual_router_id,
                rw_vip=leader_sector_vip.address,
                ro_virtual_router_id=replica_sector_vip.virtual_router_id,
                ro_vip=replica_sector_vip.address,
                replicas=form_data.replicas,
                memory_gb=form_data.memory_gb,
                cores=form_data.cores,
                capacity_gb=form_data.capacity_gb,
                storage=form_data.storage,
                sector=form_data.sector,
                application_user=form_data.application_user,
                application_database=form_data.application_database,
                superuser_password=SecretManifest.create_service_secret(
                    service_name="datacore", service_id=datacore_name, subservice_name="superuser",
                ).to_ref(),
                replication_password=SecretManifest.create_service_secret(
                    service_name="datacore", service_id=datacore_name, subservice_name="replication",
                ).to_ref(),
                application_password=SecretManifest.create_service_secret(
                    service_name="datacore",
                    service_id=datacore_name,
                    subservice_name=form_data.application_user,
                    value=form_data.application_password,
                ).to_ref(),
            ),
        )
        manifest.save()
        return manifest
