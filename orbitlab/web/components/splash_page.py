"""Splash page component for OrbitLab, displaying animated SVG graphics and initialization text."""

import random
from typing import Final

import reflex as rx

from orbitlab.data_types import ManifestKind, StorageContentType
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.cluster import ClusterManifest
from orbitlab.manifest.schemas.nodes import NodeManifest
from orbitlab.manifest.schemas.settings import OrbitLabSettingsManifest, SettingsMetadata, SettingsSpec
from orbitlab.services.discovery import Cluster, Node
from orbitlab.services.discovery.appliances import ApplianceDiscovery
from orbitlab.web.components import Buttons, Dialog, FieldSet, Input, OrbitLabLogo, Select


class SplashPageState(rx.State):
    subtitle: str = ""
    configured: bool = rx.field(
        default_factory=lambda: bool(ManifestClient().get_existing_by_kind(kind=ManifestKind.SETTINGS)),
    )
    running_discovery: bool = False
    cluster: ClusterManifest | None = None
    nodes: list[str] = rx.field(default_factory=list)
    primary_node: str = ""
    default_ha_group: str = ""

    @rx.var
    def cluster_name(self) -> str:
        if self.cluster:
            return self.cluster.name
        return "OrbitLab1"

    @rx.var
    def mode(self) -> str:
        if self.cluster:
            return "Cluster"
        return "Node"

    @rx.var
    def _primary_node_manifest(self) -> NodeManifest | None:
        if self.primary_node:
            return ManifestClient().load(self.primary_node, kind=ManifestKind.NODE)
        return None

    @rx.var
    def available_vztmpl(self) -> list[str]:
        if self._primary_node_manifest:
            return [
                store.name
                for store in self._primary_node_manifest.spec.storage.root
                if StorageContentType.VZTMPL in store.content
            ]
        return []


@rx.event(background=True)
async def run_cluster_discovery(state: SplashPageState):
    manifest_client = ManifestClient()
    async with state:
        state.running_discovery = True
        state.subtitle = "Running Cluster Discovery..."
    name = await Cluster().run()
    async with state:
        state.cluster = manifest_client.load(name, kind=ManifestKind.CLUSTER)
        state.subtitle = "Running Node Discovery..."
    await Node().run()
    async with state:
        state.subtitle = "Running Appliance Discovery..."
        state.nodes = list(manifest_client.get_existing_by_kind(kind=ManifestKind.NODE).keys())
    await ApplianceDiscovery().run()
    async with state:
        state.subtitle = "Done."
    return Dialog.close(ConfigureSettingsDialog.dialog_id)


@rx.event
async def initialize_settings(state: SplashPageState, form: dict):
    manifest = OrbitLabSettingsManifest(
        name=state.cluster_name,
        metadata=SettingsMetadata(
            cluster_mode=state.mode == "cluster",
            primary_node=state.primary_node,
        ),
        spec=SettingsSpec(),
    )
    if default_vztmpl := form.get("default_vztmpl"):
        manifest.spec.default_storage_selections.vztmpl = default_vztmpl
    ManifestClient().save(manifest=manifest)
    state.reset()
    state.configured = True
    return Dialog.open(ConfigureSettingsDialog.dialog_id)


@rx.event
async def set_primary_node(state: SplashPageState, node: str):
    state.primary_node = node


class ConfigureSettingsDialog:
    dialog_id: Final = "configure-settings-dialog"
    form_id: Final = "configure-settings-form"

    def __new__(cls) -> rx.Component:
        return Dialog(
            f"Initialize {SplashPageState.cluster_name} Settings",
            rx.el.form(
                FieldSet(
                    "General",
                    FieldSet.Field(
                        "Mode: ",
                        Input(
                            value=SplashPageState.mode,
                            form=cls.form_id,
                            name="orbitlab_mode",
                            disabled=True,
                        ),
                    ),
                    FieldSet.Field(
                        "Default Proxmox Node: ",
                        Select(
                            SplashPageState.nodes,
                            default_value=SplashPageState.primary_node,
                            on_change=set_primary_node,
                            placeholder="Select Default Proxmox Node",
                            form=cls.form_id,
                            name="primary_node",
                            required=True,
                        ),
                    ),
                ),
                FieldSet(
                    "Default Storage Configs",
                    FieldSet.Field(
                        "VZ Templates: ",
                        Select(
                            SplashPageState.available_vztmpl,
                            placeholder="Select Default Storage Option",
                            form=cls.form_id,
                            name="default_vztmpl",
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=initialize_settings,
            ),
            rx.el.div(
                Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex justify-end mt-4",
            ),
            dialog_id=cls.dialog_id,
        )


class SplashPage:
    """A splash page component for OrbitLab, displaying animated SVG graphics and initialization text."""

    def __new__(cls) -> rx.Component:
        """Create and return the SplashPage component with animated SVG graphics and initialization text."""
        return rx.box(
            rx.box(
                rx.el.svg(
                    *[
                        rx.el.circle(
                            cx=f"{x}%",
                            cy=f"{y}%",
                            r=f"{r:.1f}",
                            fill="#E8F1FF",
                            opacity="0",
                            style={"--dx": str(y), "--dy": str(x), "--duration": f"{duration}s"},
                            class_name="star",
                        )
                        for x, y, r, duration in [
                            (
                                random.randint(1, 99),  # noqa: S311
                                random.randint(1, 99),  # noqa: S311
                                random.uniform(0.1, 2.1),  # noqa: S311
                                random.randint(5, 15),  # noqa: S311
                            )
                            for _ in range(random.randint(15, 20))  # noqa: S311
                        ]
                    ],
                    xmlns="http://www.w3.org/2000/svg",
                    viewBox="0 0 200 200",
                    fill="none",
                    class_name="w-full h-full",
                ),
                class_name="absolute inset-0",
            ),
            OrbitLabLogo(size=150, animated=True),
            rx.box(
                rx.text(
                    "OrbitLab",
                    class_name="text-[#E8F1FF] font-semibold tracking-widest text-2xl mt-8 fade-title",
                ),
                rx.cond(
                    SplashPageState.configured,
                    rx.text(
                        SplashPageState.subtitle,
                        class_name="text-[#36E2F4] text-sm mt-2 fade-subtitle",
                    ),
                    rx.cond(
                        SplashPageState.running_discovery,
                        rx.text(
                            SplashPageState.subtitle,
                            class_name="text-[#36E2F4] text-sm mt-2",
                        ),
                        rx.el.div(
                            Buttons.Primary("Initialize", on_click=run_cluster_discovery),
                            class_name=(
                                "w-full flex items-center justify-center mt-6 animate-[fadeInUp_3s_ease-in-out] "
                                "relative z-10"
                            ),
                        ),
                    ),
                ),
                class_name="flex flex-col items-center justify-center",
            ),
            ConfigureSettingsDialog(),
            class_name=(
                "relative flex flex-col items-center justify-center min-h-screen w-full "
                "bg-[#0E1015] overflow-hidden select-none"
            ),
        )
