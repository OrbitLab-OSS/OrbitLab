"""Infrastructure Appliance Workflows."""

import asyncio
from typing import get_args

from orbitlab.data_types import OrbitLabApplianceType
from orbitlab.proxmox import ProxmoxComputeTemplates
from orbitlab.redis.clients import ClusterClient
from orbitlab.redis.models import InfraAppliance

from .base import Workflow, WorkflowPayload


class InfraAppliancePayload(WorkflowPayload):
    """Download Infrastructure Appliance Payload."""


class DownloadInfraApplianceV1(Workflow):
    """Download Infrastructure Appliances."""

    TYPE: str = "infrastructure.download"
    SCHEMA: str = "v1"
    PAYLOAD_TYPE: type[InfraAppliancePayload] = InfraAppliancePayload
    IDP_TOKEN: str = "ol:infrastructure:appliances"
    payload: InfraAppliancePayload

    async def validate(self) -> None:
        """Validate if appliance already exists and handle accordingly."""
        infra = await ClusterClient().get_infra_appliances()
        latest = await ProxmoxComputeTemplates().get_infrastructure_appliances()
        
        if infra.version == latest.version:
            return await self.succeed(f"OrbitLab Infrastructure already at latest version: {latest.version}")

    async def provision(self) -> InfraAppliancePayload:
        """Download the infra appliance, deleting the old one, if necessary."""
        client = ClusterClient()
        proxmox = ProxmoxComputeTemplates()
        infra = await client.get_infra_appliances()

        await self.log(f"Deleting old appliance versions: {infra.version}")
        await asyncio.gather(*[
            proxmox.delete_appliance(node=old_appliance.node, storage=old_appliance.storage, volume_id=old_appliance.volume_id)
            for old_appliance in infra.appliances.values()
        ])

        appliances = await proxmox.get_infrastructure_appliances()
        defaults = await client.get_defaults()
        for appliance_type in get_args(OrbitLabApplianceType.__value__):
            appliance = appliances.get_appliance(appliance_type=appliance_type)
            if appliance.filename.endswith(".qcow2"):
                storage = defaults.imports
                content = "import"
            else:
                storage = defaults.vztmpl
                content = "vztmpl"
                
            checksum_algorithm, checksum = appliance.digest.split(":")
            params = {
                "content": content,
                "url": appliance.browser_download_url,
                "filename": appliance.filename,
                "checksum": checksum,
                "checksum-algorithm": checksum_algorithm,
            }
            await self.log(f"Downloading {appliance_type} v{appliances.version} with params: {params}")
            volume_id = await proxmox.download_infrastructure_appliance(storage=storage, params=params, node=defaults.node)
            await self.log(f"New {appliance_type} volume ID: {volume_id}")
            infra.appliances[appliance_type] = InfraAppliance(node=defaults.node, volume_id=volume_id)
        
        infra.version = appliances.version
        await client.set_infra_appliances(appliances=infra)
        return await self.succeed(f"Successfully updated infrastructure to version {infra.version}")
