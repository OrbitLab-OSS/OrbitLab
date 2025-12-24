"""Proxmox Client Base Models."""

from typing import Annotated

from pydantic import BaseModel, Field, RootModel

from orbitlab import data_types
from orbitlab.manifest.serialization import PveBool, PveContentList, PveStorageType


class Task(RootModel[str]):
    """Proxmox Task."""

    @property
    def upid(self) -> str:
        """Get the unique process identifier (UPID) of the task."""
        return self.root

    @property
    def node(self) -> str:
        """Get the node name from the UPID."""
        return self.root.split(":")[1]


class VMID(RootModel[int]):
    """Proxmox VM ID."""


class Storage(BaseModel):
    """
    Represents a storage resource in Proxmox.

    Attributes:
        type (PveStorageType): The type of storage.
        active (PveBool): Whether the storage is active.
        content (PveContentList): List of content types supported.
        enabled (PveBool): Whether the storage is enabled.
        shared (PveBool): Whether the storage is shared.
        name (str): The name of the storage (aliased as 'storage').
        available_bytes (int): Available bytes (aliased as 'avail').
        total_bytes (int): Total bytes (aliased as 'total').
        used_bytes (int): Used bytes (aliased as 'used').
        utilization (float): Utilization ratio.
    """

    type: PveStorageType
    active: PveBool
    content: PveContentList
    enabled: PveBool
    shared: PveBool
    name: Annotated[str, Field(alias="storage")]
    available_bytes: Annotated[int, Field(alias="avail")]
    total_bytes: Annotated[int, Field(alias="total")]
    used_bytes: Annotated[int, Field(alias="used")]
    utilization: Annotated[float, Field(alias="used_fraction")]


ProxmoxStorages = RootModel[list[Storage]]


class ProxmoxTaskStatus(BaseModel):
    """Represents the status of a Proxmox task."""

    start_time: Annotated[int, Field(alias="starttime")]
    pid: int
    node: str
    pstart: int
    type: str
    upid: str
    status: data_types.TaskStatus
    id: str
    user: str
    exit_status: Annotated[str | None, Field(alias="exitstatus", default=None)]


class ContentItem(BaseModel):
    """Represents a content item in Proxmox storage."""

    id: Annotated[str, Field(alias="volid")]
    content_type: Annotated[data_types.StorageContentType, Field(alias="content")]
    format: str
    size_bytes: Annotated[int, Field(alias="size")]
    creation_time: Annotated[int, Field(alias="ctime")]


ProxmoxStorageContent = RootModel[list[ContentItem]]


class ProxmoxTermProxy(BaseModel):
    """Represents Proxmox terminal proxy configuration for VNC connections."""

    port: int
    ticket: str
    upid: str
    user: str

    def to_params(self) -> dict[str, int | str]:
        """Convert the terminal proxy data to a dictionary of parameters."""
        return {"port": self.port, "vncticket": self.ticket}


class AuthData(BaseModel):
    """Represents authentication data returned by Proxmox API."""

    csrf_prevention_token: Annotated[str, Field(alias="CSRFPreventionToken")]
    cookie: Annotated[str, Field(alias="ticket")]


class ProxmoxAuth(BaseModel):
    """Represents Proxmox authentication response."""

    data: AuthData
