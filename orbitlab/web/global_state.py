"""OrbitLab Defaults."""

from datetime import timedelta
import os
from typing import Sequence

import reflex as rx

from orbitlab import data_types
from orbitlab.proxmox import Proxmox
from orbitlab.redis import clients, models
from orbitlab.redis.exceptions import ResourceNotFoundError
from orbitlab.web.utilities import CacheBuster


class OrbitLabState(CacheBuster, rx.State):
    status: rx.Field[data_types.InitializationStatus] = rx.field(default=data_types.InitializationStatus.UNKNOWN)
    root_certificates: rx.Field[list[models.RootCert]] = rx.field(default_factory=list)
    intermediate_certificates: rx.Field[list[models.IntermediateCert]] = rx.field(default_factory=list)
    leaf_certificates: rx.Field[list[models.LeafCert]] = rx.field(default_factory=list)

    @rx.var(deps=["_cached_domain_providers"])
    async def domain_providers(self) -> list[models.DomainProvider]:
        return await clients.ClusterClient().list_domain_providers()

    @rx.var(deps=["_cached_nodes"])
    async def nodes(self) -> list[models.Node]:
        return await clients.ClusterClient().list_nodes()

    @rx.var(deps=["_cached_sectors"])
    async def sectors(self) -> list[models.Sector]:
        return await clients.SectorClient().list_sectors()

    @rx.var(deps=["_cached_base_images"])
    async def base_images(self) -> Sequence[models.BaseImage]:
        return await clients.ImagesClient().list_images(image_type="base")

    @rx.var(deps=["_cached_custom_images"])
    async def custom_images(self) -> Sequence[models.CustomImage]:
        return await clients.ImagesClient().list_images(image_type="custom")

    @rx.var(deps=["_cached_base_appliances"])
    async def base_appliances(self) -> Sequence[models.BaseAppliance]:
        return await clients.ApplianceClient().list_appliances(appliance_type="base")

    @rx.var(deps=["_cached_custom_appliances"])
    async def custom_appliances(self) -> Sequence[models.CustomAppliance]:
        return await clients.ApplianceClient().list_appliances(appliance_type="custom")

    @rx.var(deps=["_cached_instances"])
    async def instances(self) -> list[models.Instance]:
        return await clients.InstanceClient().list_instances()

    @rx.var(deps=["_cached_dockfs_clusters"])
    async def dockfs_clusters(self) -> list[models.DockFS]:
        return await clients.DockFSClient().list_dockfs_clusters()

    @rx.var(deps=["_cached_datacores"])
    async def datacores(self) -> list[models.DataCore]:
        return await clients.DataCoreClient().list_datacores()

    @rx.var(deps=["_cached_secrets"])
    async def secrets(self) -> list[models.Secret]:
        return await clients.SecretsClient().list_secrets()
    
    @rx.var(deps=["_cached_conduit_pools"])
    async def conduit_pools(self) -> list[models.ConduitPool]:
        return await clients.ConduitClient().list_pools()
    
    @rx.var(deps=["_cached_conduit_endpoints"])
    async def conduit_endpoints(self) -> list[models.ConduitEndpoint]:
        return await clients.ConduitClient().list_endpoints()
    
    @rx.var
    async def most_recent_instances(self) -> list[models.Instance]:
        by_update = sorted(
            await self.instances,
            key=lambda instance: instance.config.last_update,
            reverse=True,
        )
        if len(by_update) > 5:
            return by_update[:4]
        return by_update


class OrbitLabStats(OrbitLabState):
    
    @rx.var
    async def instance_data(self) -> dict[str, int]:
        stats = {"running": 0, "stopped": 0}
        for instance in await self.instances:
            if instance.state.status == data_types.ComputeStatus.RUNNING:
                stats["running"] += 1
            elif instance.state.status == data_types.ComputeStatus.STOPPED:
                stats["stopped"] += 1
        return stats

    @rx.var
    async def appliance_workflows(self) -> dict[str, int]:
        stats = {"succeeded": 0, "failed": 0, "total": 0}
        for appliance in await self.custom_appliances:
            if appliance.state.workflow_status == data_types.TemplateWorkflowStatus.SUCCEEDED:
                stats["succeeded"] += 1
            elif appliance.state.workflow_status == data_types.TemplateWorkflowStatus.FAILED:
                stats["failed"] += 1
            stats["total"] += 1
        return stats
    
    @rx.var
    async def image_workflows(self) -> dict[str, int]:
        stats = {"succeeded": 0, "failed": 0, "total": 0}
        for image in await self.custom_images:
            if image.state.workflow_status == data_types.TemplateWorkflowStatus.SUCCEEDED:
                stats["succeeded"] += 1
            elif image.state.workflow_status == data_types.TemplateWorkflowStatus.FAILED:
                stats["failed"] += 1
            stats["total"] += 1
        return stats

    @rx.var
    async def base_assets(self) -> dict[str, int]:
        return {
            "appliances": len(await self.base_appliances),
            "images": len(await self.base_images),
        }

    @rx.var
    def certificate_expirations(self) -> dict[str, dict[str, int]]:
        stats = {
            "expiring": {"root": 0, "intermediate": 0, "leaf": 0},
            "expired": {"root": 0, "intermediate": 0, "leaf": 0},
        }
        for cert in self.root_certificates:
            if cert.status == "warning":
                stats["expiring"]["root"] += 1
            if cert.status == "expired":
                stats["expired"]["root"] += 1
        for cert in self.intermediate_certificates:
            if cert.status == "warning":
                stats["expiring"]["intermediate"] += 1
            if cert.status == "expired":
                stats["expired"]["intermediate"] += 1
        for cert in self.leaf_certificates:
            if cert.status == "warning":
                stats["expiring"]["leaf"] += 1
            if cert.status == "expired":
                stats["expired"]["leaf"] += 1
        return stats


class InfrastructureManagementState(CacheBuster, rx.State):
    infra: rx.Field[models.InfraAppliances] = rx.field(default_factory=models.InfraAppliances.empty)

    @rx.var(deps=["_cached_current_version"])
    def current_version(self) -> str:
        return self.infra.version

    @rx.var(interval=timedelta(hours=1))
    async def latest_version(self) -> str:
        latest = await Proxmox().get_infrastructure_appliances()
        return latest.version

    @rx.var
    async def infrastructure_update_available(self) -> bool:
        return self.current_version != await self.latest_version

    @rx.var(deps=["_cached_backplane_status"])
    async def backplane_status(self) -> data_types.BackplaneStatus:
        try:
            backplane = await clients.BackplaneClient().get()
            return backplane.state.status
        except ResourceNotFoundError:
            return data_types.BackplaneStatus.PENDING

    @rx.var(deps=["_cached_backplane_version"])
    async def backplane_version(self) -> str:
        try:
            backplane = await clients.BackplaneClient().get()
            return backplane.state.version
        except ResourceNotFoundError:
            return ""

    @rx.var(deps=["_cached_etcd_status"])
    async def etcd_status(self) -> data_types.ETCDStatus:
        return await clients.ETCDClient().get_status()
    
    @rx.var(deps=["_cached_etcd_version"])
    async def etcd_version(self) -> str:
        return await clients.ETCDClient().get_version()

    @rx.var(deps=["_cached_etcd_cluster_members"])
    async def etcd_cluster_members(self) -> list[models.ETCDMember]:
        return await clients.ETCDClient().list_members()


class ETCDState(CacheBuster, rx.State):
    confirm_delete_etcd: rx.Field[bool] = rx.field(default=False)

    @rx.var(deps=["_cached_status"])
    async def status(self) -> data_types.ETCDStatus:
        return await clients.ETCDClient().get_status()

    @rx.var(deps=["_cached_version"])
    async def version(self) -> str:
        return await clients.ETCDClient().get_version()

    @rx.var(deps=["_cached_cluster_members"])
    async def cluster_members(self) -> list[models.ETCDMember]:
        return await clients.ETCDClient().list_members()

    @rx.var
    async def etcd_is_latest(self) -> bool:
        current_version = await self.get_var_value(InfrastructureManagementState.current_version)
        return current_version == await self.version


class SelectionDefaults(rx.State):
    defaults: rx.Field[models.Defaults] = rx.field(default_factory=models.Defaults.empty)

    @rx.var
    def default_node(self) -> str:
        """Get the default Proxmox node name from the cluster manifest, or an empty string if not set."""
        if self.defaults:
            return self.defaults.node
        return ""

    @rx.var
    def default_import_storage(self) -> str:
        """Get the default import storage name from the cluster manifest, or an empty string if not set."""
        if self.defaults:
            return self.defaults.imports
        return ""

    @rx.var
    def default_images_storage(self) -> str:
        """Get the default images (VM Disks) storage name from the cluster manifest, or an empty string if not set."""
        if self.defaults:
            return self.defaults.images
        return ""

    @rx.var
    def default_rootdir_storage(self) -> str:
        """Get the default rootdir storage name from the cluster manifest, or an empty string if not set."""
        if self.defaults:
            return self.defaults.rootdir
        return ""

    @rx.var
    def default_vztmpl_storage(self) -> str:
        """Get the default vztmpl storage name from the cluster manifest, or an empty string if not set."""
        if self.defaults:
            return self.defaults.vztmpl
        return ""


class SelectOptions(OrbitLabState):

    @rx.var
    def domain_validation_provider_options(self) -> dict[str, str]:
        return {str(provider).capitalize(): provider for provider in list(data_types.DomainValidationProviders)}

    @rx.var
    async def domain_provider_options(self) -> dict[str, str]:
        return {
            f"{provider.name} ({provider.provider})": provider.name
            for provider in await clients.ClusterClient().list_domain_providers()
        }

    @rx.var
    async def node_options(self) -> list[str]:
        return [node.config.name for node in await self.nodes]

    @rx.var
    async def node_storage_options(self) -> dict[str, dict[data_types.StorageContentType, list[str]]]:
        client = Proxmox()
        return {
            node: {
                content_type: await client.list_storages_for_node(node=node, content_type=content_type)
                for content_type in list(data_types.StorageContentType)
            } for node in await self.node_options
        }

    @rx.var
    async def sector_options(self) -> dict[str, str]:
        return {
            f"{sector.config.alias} ({sector.config.cidr_block})": sector.config.id
            for sector in await self.sectors
        }

    @rx.var
    async def conduit_enabled_sector_options(self) -> dict[str, str]:
        return {
            f"{sector.config.alias} ({sector.config.cidr_block})": sector.config.id
            for sector in await self.sectors if sector.state.conduit_vmid != 0
        }

    @rx.var
    async def base_appliance_options(self) -> dict[str, str]:
        return {f"{apl.config.template} ({apl.config.id})": apl.config.id for apl in await self.base_appliances}

    @rx.var
    async def custom_appliance_options(self) -> dict[str, str]:
        return {f"{apl.config.name} ({apl.config.id})": apl.config.id for apl in await self.custom_appliances}

    @rx.var
    async def all_appliance_options(self) -> dict[str, str]:
        appliances: dict[str, str] = (await self.base_appliance_options).copy()
        appliances.update((await self.custom_appliance_options).copy())
        return appliances

    @rx.var
    async def base_image_options(self) -> dict[str, str]:
        return {f"{image.config.os} ({image.config.id})": image.config.id for image in await self.base_images}

    @rx.var
    async def custom_image_options(self) -> dict[str, str]:
        return {f"{image.config.name} ({image.config.id})": image.config.id for image in await self.custom_images}

    @rx.var
    async def all_image_options(self) -> dict[str, str]:
        images: dict[str, str] = (await self.base_image_options).copy()
        images.update((await self.custom_image_options).copy())
        return images

    @rx.var
    def conduit_pool_health_check_methods(self) -> list[str]:
        return ["GET", "POST", "PUT", "PATCH"]

    @rx.var
    def conduit_pool_balance_options(self) -> dict[str, str]:
        return {
            "Weighted Round Robin": "wrr",
            "Power of Two Choices": "p2c",
            "Highest Random Weight": "hrw",
            "Least-Time": "leasttime"
        }

    @rx.var
    def conduit_pool_type_options(self) -> dict[str, str]:
        return {
            "HTTP": "http",
            "TCP": "tcp",
            "UDP": "udp",
        }

    @rx.var
    async def conduit_pool_options(self) -> dict[str, dict[str, str]]:
        sector_to_pools_map = {}
        for pool in await self.conduit_pools:
            if pool.config.sector not in sector_to_pools_map:
                sector_to_pools_map[pool.config.sector] = {}
            sector_to_pools_map[pool.config.sector][f"{pool.config.name} ({pool.config.id})"] = pool.config.id
        return sector_to_pools_map
