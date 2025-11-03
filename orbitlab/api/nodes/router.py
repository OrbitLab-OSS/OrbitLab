"""API router for managing nodes in the OrbitLab Proxmox cluster."""

from fastapi import APIRouter

from orbitlab.api.nodes.models import ListNodesResponse
from orbitlab.data_types import ManifestKind
from orbitlab.manifest.client import ManifestClient

router = APIRouter(prefix="/api/v1/nodes", tags=["Nodes"])


@router.get("/", response_model=ListNodesResponse)
async def list_nodes() -> ListNodesResponse:
    """Retrieves a sorted list of nodes in the OrbitLab Proxmox cluster.

    Returns:
        ListNodesResponse: An object containing the sorted list of node names.
    """
    return ListNodesResponse(nodes=sorted(ManifestClient().get_existing_by_kind(kind=ManifestKind.NODE)))
