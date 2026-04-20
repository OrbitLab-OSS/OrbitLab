"""OrbitLab Defaults."""

from datetime import timedelta

import reflex as rx

from orbitlab import data_types
from orbitlab.proxmox import Proxmox
from orbitlab.proxmox.compute_templates import ProxmoxComputeTemplates
from orbitlab.redis import clients, models
from orbitlab.web.utilities import CacheBuster


class OrbitLabState(CacheBuster, rx.State):
    initialized: rx.Field[bool] = rx.field(default=False)
    root_certificates: rx.Field[list[models.RootCert]] = rx.field(default_factory=list)
    intermediate_certificates: rx.Field[list[models.IntermediateCert]] = rx.field(default_factory=list)
    leaf_certificates: rx.Field[list[models.LeafCert]] = rx.field(default_factory=list)

    @rx.var(deps=["_cached_nodes"])
    async def nodes(self) -> list[models.Node]:
        return await clients.ClusterClient().list_nodes()

    @rx.var(deps=["_cached_sectors"])
    async def sectors(self) -> list[models.Sector]:
        return await clients.SectorClient().list_sectors()

    @rx.var(deps=["_cached_base_images"])
    async def base_images(self) -> list[models.BaseImage]:
        return await clients.ImagesClient().list_images(image_type="base")

    @rx.var(deps=["_cached_custom_images"])
    async def custom_images(self) -> list[models.CustomImage]:
        return await clients.ImagesClient().list_images(image_type="custom")

    @rx.var(deps=["_cached_base_appliances"])
    async def base_appliances(self) -> list[models.BaseAppliance]:
        return await clients.ApplianceClient().list_appliances(appliance_type="base")

    @rx.var(deps=["_cached_custom_appliances"])
    async def custom_appliances(self) -> list[models.CustomAppliance]:
        return await clients.ApplianceClient().list_appliances(appliance_type="custom")

    @rx.var(deps=["_cached_lxc_instances"])
    async def lxc_instances(self) -> list[models.LXCInstance]:
        return await clients.LXCClient().list_instances()

    @rx.var(deps=["_cached_vm_instances"])
    async def vm_instances(self) -> list[models.VMInstance]:
        return await clients.VMClient().list_instances()

    @rx.var(deps=["_cached_dockfs_clusters"])
    async def dockfs_clusters(self) -> list[models.DockFS]:
        return await clients.DockFSClient().list_dockfs_clusters()

    @rx.var(deps=["_cached_datacores"])
    async def datacores(self) -> list[models.DataCore]:
        return await clients.DataCoreClient().list_datacores()

    @rx.event
    async def on_load(self) -> None:
        self.initialized = await clients.ClusterClient().is_initialized()
        if self.initialized:
            self.root_certificates = await clients.PKIClient().list_root_certificates()
            self.intermediate_certificates = await clients.PKIClient().list_intermediate_certificates()
            self.leaf_certificates = await clients.PKIClient().list_leaf_certificates()
            return [
                SelectionDefaults.reload,
                InfrastructureManagementState.reload,
            ]


class InfrastructureManagementState(OrbitLabState):
    infra: rx.Field[models.InfraAppliances | None] = rx.field(default=None)

    @rx.var(interval=timedelta(hours=1))
    async def latest_version(self) -> str:
        latest = await ProxmoxComputeTemplates().get_infrastructure_appliances()
        return latest.version

    @rx.var
    def current_version(self) -> str:
        if self.infra:
            return self.infra.version
        return ""

    @rx.var
    async def infrastructure_update_available(self) -> bool:
        return self.current_version != await self.latest_version

    @rx.event
    async def reload(self) -> None:
        self.infra = await clients.ClusterClient().get_infra_appliances()


class ETCDState(CacheBuster, rx.State):

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
    
    @rx.var
    async def etcd_mutation_in_progress(self) -> bool:
        mutation_states = (data_types.ETCDStatus.PENDING, data_types.ETCDStatus.UPGRADING, data_types.ETCDStatus.DELETING)
        return await self.status in mutation_states


class SelectionDefaults(CacheBuster, rx.State):
    defaults: rx.Field[models.Defaults | None] = rx.field(default=None)

    @rx.var
    async def default_node(self) -> str:
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

    @rx.event
    async def reload(self) -> None:
        self.defaults = await clients.ClusterClient().get_defaults()


class SelectOptions(OrbitLabState):

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
