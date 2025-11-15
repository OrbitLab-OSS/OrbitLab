"""Models for node-related API responses in the OrbitLab Proxmox web services."""

from pydantic import BaseModel


class ListNodesResponse(BaseModel):
    """Response model containing a list of nodes.

    Attributes:
        nodes (list[ListedNode]): The list of nodes returned in the response.
    """

    nodes: list[str]
