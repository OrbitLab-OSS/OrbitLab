"""Infrastructure Appliance Workflows."""

import asyncio
from typing import get_args

from orbitlab.data_types import OrbitLabApplianceType
from orbitlab.manifest.cluster import ClusterManifest, InfraAppliance

from .base import Workflow, WorkflowPayload
from .utilities import InfraUtils


class InfraAppliancePayload(WorkflowPayload):
    """Download Infrastructure Appliance Payload."""


class DownloadInfraApplianceV1(Workflow, InfraUtils):
    """Download Infrastructure Appliances."""

    TYPE: str = "infrastructure.download"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[InfraAppliancePayload] = InfraAppliancePayload
    payload: InfraAppliancePayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        
        if manifest.metadata.infrastructure_version:
            latest = self.proxmox_compute_templates.get_infrastructure_appliances()
            if manifest.metadata.infrastructure_version == latest.version:
                await self.succeed(f"OrbitLab Infrastructure already at latest version: {latest.version}")
                return

    async def provision(self) -> InfraAppliancePayload:
        """Download the infra appliance, deleting the old one, if necessary."""
        manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))

        await asyncio.gather(*[
            self.remove_old_appliance(old_appliance=old_appliance)
            for old_appliance in manifest.metadata.infrastructure_appliances
        ])

        appliances = self.proxmox_compute_templates.get_infrastructure_appliances()
        downloaded: list[tuple[OrbitLabApplianceType, InfraAppliance]] = await asyncio.gather(*[
            self.download_infrastructure_appliance(
                appliance_type=appliance_type,
                appliance=appliances.get_appliance(appliance_type=appliance_type),
            ) for appliance_type in get_args(OrbitLabApplianceType.__value__)
        ])
        manifest.metadata.infrastructure_appliances = {
            appliance_type: appliance for appliance_type, appliance in downloaded
        }
        manifest.metadata.infrastructure_version = appliances.version
        manifest.save()
        return await self.succeed(f"Successfully updated infrastructure to version {manifest.metadata.infrastructure_version}")
