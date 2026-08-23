"""PVE 9 response-schema coverage for the Proxmox adapter boundary."""

from orbitlab.proxmox.models import (
    ProxmoxBridges,
    ProxmoxClusterStatus,
    ProxmoxComputeResources,
    ProxmoxStorages,
    ProxmoxTaskStatus,
    ProxmoxVnets,
    SDNControllers,
)
from tests.fixtures.proxmox_9 import BRIDGES, CLUSTER_RESOURCES, CLUSTER_STATUS, SDN_CONTROLLERS, STORAGE, TASK_STATUS, VNets


def test_proxmox_9_cluster_resource_fixture_is_discoverable() -> None:
    resources = ProxmoxComputeResources.model_validate(CLUSTER_RESOURCES)

    assert resources.get_resource(101).node == "pve-a"
    assert resources.get_resource(102).type == "qemu"


def test_proxmox_9_task_fixture_preserves_upid_node_and_success() -> None:
    task = ProxmoxTaskStatus.model_validate(TASK_STATUS)

    assert task.node == "pve-a"
    task.raise_for_status()


def test_proxmox_9_storage_fixture_parses_zero_and_one_booleans() -> None:
    storage = ProxmoxStorages.model_validate(STORAGE).root[0]

    assert storage.active is True
    assert storage.shared is False


def test_proxmox_9_cluster_network_and_sdn_fixtures_cover_bootstrap_discovery() -> None:
    cluster = ProxmoxClusterStatus.model_validate(CLUSTER_STATUS)
    bridges = ProxmoxBridges.model_validate(BRIDGES)
    vnets = ProxmoxVnets.model_validate(VNets)
    controllers = SDNControllers.model_validate(SDN_CONTROLLERS)

    assert [node.name for node in cluster.list_nodes()] == ["pve-a", "pve-b"]
    assert str(bridges.get_vmbr0().cidr.network) == "192.0.2.0/24"
    assert vnets.get_all_tags() == [120, 121]
    assert controllers.get_evpn_controller().controller == "orbitlab"  # type: ignore[union-attr]
