"""Discovery Service base."""

from abc import ABC, abstractmethod

from orbitlab.clients.proxmox.client import Proxmox
from orbitlab.constants import MANIFEST_ROOT
from orbitlab.data_types import ManifestKind
from orbitlab.manifest.client import ManifestClient


class DiscoveryService(ABC):
    """Abstract base class for discovery services that handle different ManifestKind types.

    This class provides a template for implementing discovery logic for various manifest kinds.
    """

    def __init__(self, *, kind: ManifestKind, proxmox: Proxmox | None = None) -> None:
        """Initialize the DiscoveryService with a specific ManifestKind.

        Args:
            kind (ManifestKind): The kind of manifest(s) to be discovered.
            proxmox (Proxmox | None): A Proxmox client instance. If not provided, a new instance will be created.
        """
        self._kind = kind
        self._filepath = MANIFEST_ROOT / "services" / "discovery" / f"{self._kind.value}.yaml"
        self.proxmox = proxmox or Proxmox()
        self.manifests = ManifestClient()

        self._filepath.parent.mkdir(exist_ok=True, parents=True)

    @abstractmethod
    def run(self) -> None:
        """Run the discovery service.

        This method should be implemented by subclasses to perform the discovery logic.
        """
