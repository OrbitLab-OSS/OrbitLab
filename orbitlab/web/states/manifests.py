"""OrbitLab Manifests States."""

import reflex as rx

from orbitlab.data_types import CertificateTypes
from orbitlab.manifest.appliances import BaseApplianceManifest, CustomApplianceManifest
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.manifest.nodes import NodeManifest
from orbitlab.manifest.secrets import CertificateManifest, SecretManifest
from orbitlab.manifest.sector import SectorManifest

from .utilities import CacheBuster


class ManifestsState(CacheBuster, rx.State):
    """State management for certificate manifests."""

    @rx.var
    def nodes(self) -> list[NodeManifest]:
        """Get all existing node manifests."""
        return [NodeManifest.load(name=name) for name in NodeManifest.get_existing()]

    @rx.var(deps=["_cached_certificates"])
    def certificates(self) -> list[CertificateManifest]:
        """Get all existing certificate manifests."""
        return [CertificateManifest.load(name=name) for name in CertificateManifest.get_existing()]

    @rx.var(deps=["_cached_secrets"])
    def secrets(self) -> list[SecretManifest]:
        """Get all existing secret manifests."""
        return [SecretManifest.load(name=name) for name in SecretManifest.get_existing()]

    @rx.var(deps=["_cached_base_appliances"])
    def base_appliances(self) -> list[BaseApplianceManifest]:
        """Get all existing base appliance manifests."""
        return [BaseApplianceManifest.load(name=name) for name in BaseApplianceManifest.get_existing()]

    @rx.var(deps=["_cached_custom_appliances"])
    def custom_appliances(self) -> list[CustomApplianceManifest]:
        """Get all existing custom appliance manifests."""
        return [CustomApplianceManifest.load(name=name) for name in CustomApplianceManifest.get_existing()]

    @rx.var(deps=["_cached_sectors"])
    def sectors(self)-> list[SectorManifest]:
        """Get all existing sector manifests."""
        return [SectorManifest.load(name=name) for name in SectorManifest.get_existing()]

    @rx.var
    def node_names(self) -> list[str]:
        """Get a list of node names from all node manifests."""
        return [node.name for node in self.nodes]

    @rx.var
    def base_appliance_names(self) -> list[str]:
        """Get a list of base appliance names from all base appliance manifests."""
        return [appliance.name for appliance in self.base_appliances]

    @rx.var
    def certificate_authorities(self) -> list[CertificateManifest]:
        """Get all root certificate authority manifests from the certificates list."""
        return [cert for cert in self.certificates if cert.metadata.type == CertificateTypes.ROOT]

    @rx.var
    def certificate_authority_names(self) -> list[str]:
        """Get a list of certificate authority names."""
        return [cert.name for cert in self.certificate_authorities]

    @rx.var
    def intermediate_certificates(self) -> list[CertificateManifest]:
        """Get all root certificate authority manifests from the certificates list."""
        return [cert for cert in self.certificates if cert.metadata.type == CertificateTypes.INTERMEDIATE]


class ClusterDefaults(ManifestsState):
    """State management for cluster default settings."""

    @rx.var
    def proxmox_node(self) -> str:
        """Get the default Proxmox node name from the cluster manifest, or an empty string if not set."""
        name = next(iter(ClusterManifest.get_existing()), "")
        if name:
            cluster = ClusterManifest.load(name=name)
            return cluster.spec.defaults.node
        return ""
