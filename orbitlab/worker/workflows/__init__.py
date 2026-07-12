"""LXC Workflows.

Import the workflow and add it to the list below to enable workflow registration.
"""

from .appliances import ApplianceDeleteV1, ApplianceDownloadV1, CreateCustomApplianceV1
from .base import Workflow
from .conduit import ConduitPoolCreateV1, ConduitEndpointCreateV1, ConduitHealthV1, ConduitPoolDeleteV1, ConduitDeleteV1
from .datacore import CreateDataCoreCluster, DeleteDataCoreCluster, DataCoreClusterEvent
from .etcd import UpgradeETCDClusterV1, ETCDMemberFailoverV1
from .dockfs import CreateDockFsV1, DeleteDockFsV1, FailoverDockFsV1
from .images import CreateCustomImageV1, ImageDeleteV1, ImageDownloadV1
from .sectors import CreateSectorV1, SectorConduitCreateV1, SectorGatewayUpdateV1, SectorConduitUpdateV1, SectorConduitSyncV1, DeleteSectorV1
from .infra import DownloadInfraApplianceV1, UpgradeBackplaneV1, ProbeRelayV1
from .instances import InstanceCreateV1, AquireInstanceIpAddress, InstanceStateChangeV1, InstanceDHCPChange

workflows = [
    ApplianceDownloadV1,
    ApplianceDeleteV1,
    CreateCustomApplianceV1,
    InstanceCreateV1,
    InstanceStateChangeV1,
    AquireInstanceIpAddress,
    ImageDownloadV1,
    ImageDeleteV1,
    CreateCustomImageV1,
    CreateSectorV1,
    DeleteSectorV1,
    CreateDockFsV1,
    FailoverDockFsV1,
    DeleteDockFsV1,
    ETCDMemberFailoverV1,
    CreateDataCoreCluster,
    DeleteDataCoreCluster,
    DataCoreClusterEvent,
    DownloadInfraApplianceV1,
    UpgradeETCDClusterV1,
    InstanceDHCPChange,
    UpgradeBackplaneV1,
    ProbeRelayV1,
    SectorConduitCreateV1,
    ConduitPoolCreateV1,
    ConduitEndpointCreateV1,
    ConduitHealthV1,
    ConduitDeleteV1,
    ConduitPoolDeleteV1,
    SectorConduitUpdateV1,
    SectorConduitSyncV1,
    SectorGatewayUpdateV1
]

__all__ = (
    "Workflow",
    "workflows",
)
