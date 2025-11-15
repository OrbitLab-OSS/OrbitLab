from typing import Final

import reflex as rx
from pydantic import BaseModel, Field

from orbitlab.clients.proxmox.client import Proxmox
from orbitlab.clients.proxmox.models import ApplianceInfo
from orbitlab.data_types import ApplianceType, ManifestKind
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.appliances import BaseApplianceManifest, BaseApplianceMetadata, BaseApplianceSpec
from orbitlab.manifest.schemas.nodes import NodeManifest
from orbitlab.web.components import Buttons, GridList, Input, OrbitLabLogo, RadioGroup, Select
from orbitlab.web.states.cluster import OrbitLabSettings
from orbitlab.web.states.managers import DialogStateManager


class ApplianceItemDownload(BaseModel):
    node: str = ""
    storage: str = ""
    available_storage: list[str] = Field(default_factory=list)
    downloading: bool = False


class DownloadApplianceState(rx.State):
    appliance_view: ApplianceType = ApplianceType.SYSTEM
    query_string: str = ""
    download_configs: dict[str, ApplianceItemDownload] = rx.field(default_factory=dict)
    existing: list[str] = rx.field(
        default_factory=lambda: ManifestClient().get_existing_by_kind(kind=ManifestKind.BASE_APPLIANCE),
    )

    @rx.var
    def available_appliances(self) -> list[ApplianceInfo]:
        appliances = []
        try:
            node = next(iter(ManifestClient().get_existing_by_kind(kind=ManifestKind.NODE).keys()))
        except StopIteration:
            return appliances
        else:
            download_configs = {}
            for appliance in Proxmox().list_appliances(node=node).root:
                if appliance.template in self.existing:
                    continue
                appliances.append(appliance)
                download_configs[appliance.template] = ApplianceItemDownload()
            self.download_configs = download_configs
        return sorted(appliances, key=lambda apl: apl.template)

    @rx.var
    def available_system_appliances(self) -> list[ApplianceInfo]:
        system_appliances = []
        for apl in self.available_appliances:
            if apl.is_turnkey:
                continue
            if self.query_string and self.query_string not in apl.template.lower():
                continue
            system_appliances.append(apl)
        return system_appliances

    @rx.var
    def available_turnkey_appliances(self) -> list[ApplianceInfo]:
        turnkey_appliances = []
        for apl in self.available_appliances:
            if not apl.is_turnkey:
                continue
            if self.query_string and self.query_string not in apl.template.lower():
                continue
            turnkey_appliances.append(apl)
        return turnkey_appliances

    @rx.var
    def available_nodes(self) -> list[str]:
        return list(ManifestClient().get_existing_by_kind(kind=ManifestKind.NODE))


@rx.event
async def set_node(state: DownloadApplianceState, template: str, node: str):
    node_manifest: NodeManifest = ManifestClient().load(node, kind=ManifestKind.NODE)
    state.download_configs[template].node = node
    state.download_configs[template].available_storage = [
        store.name for store in node_manifest.spec.storage.root if "vztmpl" in store.content
    ]


@rx.event(background=True)
async def wait_for_download(state: DownloadApplianceState, manifest: BaseApplianceManifest, upid: str):
    try:
        Proxmox().wait_for_task(node=manifest.spec.node, upid=upid)
    except TimeoutError:
        return rx.toast.error(f"Downloading {manifest.name} timed out after 15 min.")
    else:
        ManifestClient().save(manifest=manifest)
        return rx.toast.success(f"Appliance {manifest.name} download complete!")
    finally:
        async with state:
            state.download_configs[manifest.name].downloading = False
            state.existing = list(ManifestClient().get_existing_by_kind(kind=ManifestKind.BASE_APPLIANCE).keys())


@rx.event
async def download_appliance(state: DownloadApplianceState, form: dict):
    template = form["template"]
    node = form["node"]
    storage = form["storage"]
    state.download_configs[template].downloading = True
    appliance = next(iter(apl for apl in state.available_system_appliances if apl.template == template))
    manifest = BaseApplianceManifest(
        name=appliance.template,
        metadata=BaseApplianceMetadata(
            turnkey=appliance.is_turnkey,
            section=appliance.section,
            info=appliance.headline,
            checksum=appliance.sha512sum,
            url=appliance.location,
        ),
        spec=BaseApplianceSpec(
            node=node,
            template=appliance.template,
            storage=storage,
            architecture=appliance.architecture,
            version=appliance.version,
            os_type=appliance.os,
        ),
    )
    upid = Proxmox().download_appliance(node=manifest.spec.node, storage=manifest.spec.storage, appliance=appliance)
    return [
        DialogStateManager.toggle(DownloadApplianceDialog.dialog_id),
        wait_for_download(manifest, upid),
    ]


@rx.event
async def set_appliance_view(state: DownloadApplianceState, appliance_view: str):
    state.appliance_view = ApplianceType(appliance_view)


@rx.event
async def search_appliances(state: DownloadApplianceState, query: str):
    state.query_string = query.lower()


class DownloadApplianceDialog:
    dialog_id: Final = "download-appliance-dialog"
    form_id: Final = "download-appliance-form"

    @classmethod
    def __appliance__(cls, appliance: ApplianceInfo) -> rx.Component:
        """Create a grid list item component for a system appliance."""
        return GridList.Item(
            rx.el.div(
                rx.el.div(
                    rx.el.h3(
                        appliance.template,
                        class_name=("text-lg font-semibold text-gray-900 dark:text-[#E8F1FF] truncate"),
                    ),
                    rx.el.p(
                        f"{appliance.type} • {appliance.version} • {appliance.architecture}",
                        class_name="text-sm text-gray-500 dark:text-gray-400 mt-1",
                    ),
                    class_name="mb-3",
                ),
                rx.el.p(
                    appliance.headline,
                    class_name="text-sm text-gray-700 dark:text-gray-300 line-clamp-3 mb-3",
                ),
            ),
            rx.el.div(
                rx.form(
                    rx.el.input(
                        form=f"form-{appliance.template}",
                        name="template",
                        value=appliance.template,
                        class_name="hidden",
                    ),
                    Select(
                        DownloadApplianceState.available_nodes,
                        default_value=OrbitLabSettings.primary_node,
                        placeholder="Select Node",
                        name="node",
                        required=True,
                        on_change=lambda node: set_node(appliance.template, node),
                    ),
                    Select(
                        DownloadApplianceState.download_configs[appliance.template].available_storage,
                        placeholder="Select Storage",
                        name="storage",
                        required=True,
                    ),
                    id=f"form-{appliance.template}",
                    on_submit=download_appliance,
                ),
                rx.cond(
                    DownloadApplianceState.download_configs[appliance.template].downloading,
                    OrbitLabLogo(size=38, animated=True),
                    Buttons.Primary("Download", form=f"form-{appliance.template}"),
                ),
                class_name="flex flex-col items-center justify-center",
            ),
        )

    def __new__(cls) -> rx.Component:
        """Create and return the download appliance dialog component.

        Returns:
            rx.Component: A dialog component for downloading Proxmox appliances.
        """
        return rx.dialog.root(
            rx.dialog.content(
                rx.el.form(id=cls.form_id, on_submit=download_appliance),
                rx.dialog.title("Select Appliance to Download"),
                rx.el.div(
                    RadioGroup(
                        RadioGroup.Item(
                            "system",
                            on_change=lambda: set_appliance_view("system"),
                            value=DownloadApplianceState.appliance_view,
                        ),
                        RadioGroup.Item(
                            "turnkey",
                            on_change=lambda: set_appliance_view("turnkey"),
                            value=DownloadApplianceState.appliance_view,
                        ),
                    ),
                    Input(placeholder="Search appliances...", icon="search", on_change=search_appliances),
                    class_name="flex items-center justify-between mb-4 space-x-4",
                ),
                rx.scroll_area(
                    rx.vstack(
                        rx.match(
                            DownloadApplianceState.appliance_view,
                            (
                                ApplianceType.TURNKEY,
                                GridList(
                                    rx.foreach(
                                        DownloadApplianceState.available_turnkey_appliances,
                                        lambda apl: cls.__appliance__(apl),
                                    ),
                                ),
                            ),
                            GridList(
                                rx.foreach(
                                    DownloadApplianceState.available_system_appliances,
                                    lambda apl: cls.__appliance__(apl),
                                ),
                            ),
                        ),
                    ),
                    type="hover",
                    scrollbars="vertical",
                    class_name="flex-grow",
                ),
                rx.el.div(
                    Buttons.Secondary("Close", on_click=DialogStateManager.toggle(DownloadApplianceDialog.dialog_id)),
                    class_name="w-full flex justify-end mt-4",
                ),
                class_name="max-w-[85vw] w-[85vw] max-h-[85vh] h-[85vh] flex flex-col",
            ),
            on_mount=DialogStateManager.register(cls.dialog_id),
            open=DialogStateManager.registered.get(cls.dialog_id, False),
            class_name=(
                "border-r border-gray-200 dark:border-white/[0.08] "
                "transition-all duration-300 ease-in-out "
                "bg-gradient-to-b from-gray-50/95 to-gray-200/80 "
                "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)] "
                "hover:ring-1 hover:ring-[#36E2F4]/30"
            ),
        )
