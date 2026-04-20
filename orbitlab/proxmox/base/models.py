"""Proxmox Client Base Models."""

import ipaddress
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, RootModel

from orbitlab import data_types


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
    """Represents a storage resource in Proxmox."""

    type: data_types.PveStorageType
    active: data_types.PveBool
    content: data_types.PveContentList
    enabled: data_types.PveBool
    shared: data_types.PveBool
    name: str = Field(alias="storage")
    available_bytes: int = Field(alias="avail")
    total_bytes: int = Field(alias="total")
    used_bytes: int = Field(alias="used")
    utilization: float = Field(alias="used_fraction")


class ProxmoxStorages(RootModel[list[Storage]]):
    """Represents a collection of Proxmox storage resources with utility methods."""

    def list_all(self) -> list[str]:
        """Return a list of all storage names."""
        return [store.name for store in self.root]


class ProxmoxTaskError(Exception):
    """"""


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
    
    def raise_for_status(self) -> None:
        if self.exit_status != "OK":
            raise ProxmoxTaskError(self.exit_status)


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
    
    @classmethod
    def from_pvesh(cls, data: str) -> Self:
        return cls(data=AuthData.model_validate_json(data))


class VMClusterResource(BaseModel):
    """Represents a VM cluster resource with its VM ID and node name."""

    vmid: int
    node: str


class VMClusterResources(RootModel[list[VMClusterResource]]):
    """Represents a collection of VM cluster resources with utility methods."""

    def get_node(self, vmid: int) -> str:
        """Get the node name for a given VM ID."""
        return next(iter(vm.node for vm in self.root if vm.vmid == vmid), "")


class NodeStatus(BaseModel):
    """Represents the status of a Proxmox cluster node."""

    node_id: Annotated[int, Field(alias="nodeid")]
    local: data_types.PveBool
    online: data_types.PveBool
    type: Literal["node"]
    ip: ipaddress.IPv4Address | None = None
    name: str
    maintenance_mode: bool = False


class ClusterStatus(BaseModel):
    """Represents the status of a Proxmox cluster."""

    name: str
    quorate: data_types.PveBool
    type: Literal["cluster"]
    quorate: bool
    version: int
    nodes: int


class ProxmoxClusterStatus(RootModel[list[Annotated[ClusterStatus | NodeStatus, Field(discriminator="type")]]]):
    """Represents the status of a Proxmox cluster including nodes and cluster information."""

    def get_nodes(self) -> list[NodeStatus]:
        """Get all nodes from the cluster status."""
        return [item for item in self.root if isinstance(item, NodeStatus)]

    def get_node(self, name: str) -> NodeStatus:
        return next(iter([item for item in self.root if isinstance(item, NodeStatus) and item.name == name]))

    def get_local_node(self) -> str:
        """Get the name of the local node from the cluster status."""
        return next(iter(node.name for node in self.get_nodes() if node.local))

    def get_cluster(self) -> ClusterStatus | None:
        """Get the cluster status from the cluster status list."""
        return next(iter(item for item in self.root if isinstance(item, ClusterStatus)), None)


class QemuConfig(BaseModel):
    """Represents QEMU configuration for a compute instance."""

    agent: str
    scsi0: str

    @property
    def agent_enabled(self) -> bool:
        """If the Qemu Guest Agent is enabled on the VM."""
        return self.agent == "enabled=1"

    @property
    def root_volume_id(self) -> str:
        volume_id, _ = self.scsi0.split(",")
        return volume_id


class AgentExecStatus(BaseModel):
    """Represents the execution status of an agent command in Proxmox."""

    exited: data_types.PveBool
    stderr: str = Field(alias="err-data", default="")
    stdout: str = Field(alias="out-data", default="")
    exitcode: int | None = None
    signal: int | None = None

    @property
    def logs(self) -> list[str]:
        """Return combined non-empty lines from stdout and stderr as a list of log entries."""
        formatted_logs = [line for line in self.stdout.split("\n") if line]
        formatted_logs.extend([line for line in self.stderr.split("\n") if line])
        return formatted_logs


class AgentExecPid(BaseModel):
    """Represents the process ID of an agent execution in Proxmox."""

    pid: int
