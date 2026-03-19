"""LXC Workflows.

Import the workflow and add it to the list below to enable workflow registration.
"""

from .appliances import ApplianceDeleteV1, ApplianceDownloadV1, CreateCustomApplianceV1
from .base import Workflow
from .certificates import (
    CreateIntermediateCertificateAuthorityV1,
    CreateLeafCertificateV1,
    CreateRootCertificateAuthorityV1,
    DeleteCertificateV1,
)
from .datacore import (
    CreateDataCoreCluster,
    CreateETCDClusterV1,
    DeleteDataCoreCluster,
    DeleteETCDClusterV1,
    ETCDMemberFailoverV1,
    DataCoreClusterEvent,
)
from .dockfs import CreateDockFsV1, DeleteDockFsV1, FailoverDockFsV1, ReconcileDockFsV1
from .images import CreateCustomImageV1, ImageDeleteV1, ImageDownloadV1, ImageUpdateV1
from .lxc import LXCCreateV1, LXCStateChangeV1
from .sectors import CreateSectorV1, DeleteSectorV1
from .vms import AquireVMIpAddress, VMCreateV1, VMStateChangeV1
from .infra import DownloadInfraApplianceV1

workflows = [
    LXCCreateV1,
    LXCStateChangeV1,
    ApplianceDownloadV1,
    ApplianceDeleteV1,
    CreateCustomApplianceV1,
    VMCreateV1,
    VMStateChangeV1,
    AquireVMIpAddress,
    ImageDownloadV1,
    ImageDeleteV1,
    CreateCustomImageV1,
    CreateIntermediateCertificateAuthorityV1,
    CreateLeafCertificateV1,
    CreateRootCertificateAuthorityV1,
    DeleteCertificateV1,
    CreateSectorV1,
    DeleteSectorV1,
    CreateDockFsV1,
    FailoverDockFsV1,
    ReconcileDockFsV1,
    DeleteDockFsV1,
    CreateETCDClusterV1,
    DeleteETCDClusterV1,
    ETCDMemberFailoverV1,
    CreateDataCoreCluster,
    DeleteDataCoreCluster,
    DataCoreClusterEvent,
    ImageUpdateV1,
    DownloadInfraApplianceV1,
]

__all__ = (
    "Workflow",
    "workflows",
)
