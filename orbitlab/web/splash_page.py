"""Splash page component for OrbitLab, displaying animated SVG graphics and initialization text."""

import random
from ipaddress import IPv4Network
from typing import Final

import reflex as rx

from orbitlab.clients.proxmox import ProxmoxNetworks
from orbitlab.clients.proxmox.appliances import ProxmoxAppliances
from orbitlab.constants import NetworkSettings
from orbitlab.data_types import ClusterMode, FrontendEvents, InitializationState, OrbitLabApplianceType
from orbitlab.manifest.cluster import ClusterManifest
from orbitlab.services.discovery import DiscoveryService
from orbitlab.web.components import Buttons, Callout, Dialog, FieldSet, Input, OrbitLabLogo, Select
from orbitlab.web.states.utilities import EventGroup


def _initialized() -> InitializationState:
    existing = ClusterManifest.get_existing()
    if existing and ClusterManifest.load(name=next(iter(existing))).metadata.initialized:
        return InitializationState.COMPLETE
    return InitializationState.NOT_STARTED


class SplashPageState(rx.State):
    """State management for the OrbitLab splash page and initialization process."""

    subtitle: rx.Field[str] = rx.field(default="")
    initialization_state: rx.Field[InitializationState] = rx.field(default_factory=_initialized)
    initialization_error: rx.Field[str] = rx.field(default="")
    nodes: rx.Field[list[str]] = rx.field(default_factory=list)
    vztmpls: rx.Field[list[str]] = rx.field(default_factory=list)
    rootdirs: rx.Field[list[str]] = rx.field(default_factory=list)
    backups: rx.Field[list[str]] = rx.field(default_factory=list)
    images: rx.Field[list[str]] = rx.field(default_factory=list)
    snippets: rx.Field[list[str]] = rx.field(default_factory=list)
    isos: rx.Field[list[str]] = rx.field(default_factory=list)
    imports: rx.Field[list[str]] = rx.field(default_factory=list)
    cluster_mode: rx.Field[ClusterMode | None] = rx.field(default=None)

    @rx.var
    def storage_profiles(self) -> dict[str, str]:
        """Return available storage profiles for OrbitLab configuration."""
        match self.cluster_mode:
            case ClusterMode.LOCAL:
                return {"Local (ZFS/LVM)": "local"}  # TODO: detect ZFS/LVM configurations
            case ClusterMode.CLUSTER:
                return {
                    "Local (ZFS/LVM)": "local",
                    "Shared (LINSTOR)": "linstor",
                }
            case _:
                return {}


class ConfigureDefaultsDialog(EventGroup):
    """Dialog for storage profile and defaults."""

    @classmethod
    def run_download(cls) -> None:
        """Download the latest OrbitLab gateway appliance and update the cluster manifest."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        # TODO: Use storage from selected profile
        latest_gateway = ProxmoxAppliances().download_latest_orbitlab_appliance(
            storage="local",
            appliance_type=OrbitLabApplianceType.SECTOR_GATEWAY,
        )
        cluster_manifest.metadata.gateway_appliance = latest_gateway
        cluster_manifest.save()

    @staticmethod
    @rx.event(background=True)
    async def setup_appliances(state: SplashPageState) -> None:
        """Download and configure appliances for the cluster."""
        async with state:
            state.subtitle = "Downloading latest appliances..."
        await rx.run_in_thread(ConfigureDefaultsDialog.run_download)
        async with state:
            state.initialization_state = InitializationState.COMPLETE

    @staticmethod
    @rx.event
    async def configure_defaults(state: SplashPageState, form: dict) -> FrontendEvents:
        """Finalize OrbitLab settings by saving the cluster manifest with user-provided configuration."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        cluster_manifest.spec.defaults.storage_profile = form["storage_profile"]
        cluster_manifest.spec.defaults.node = form.get("primary_node", "")
        cluster_manifest.save()
        async with state:
            state.initialization_state = InitializationState.RUNNING
        return [
            Dialog.close(ConfigureDefaultsDialog.dialog_id),
            ConfigureDefaultsDialog.setup_appliances,
        ]

    dialog_id: Final = "configure-defaults-dialog"
    form_id: Final = "configure-defaults-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return Dialog(
            "Configure OrbitLab Defaults",
            rx.el.form(
                Callout(
                    "All except the Storage Profile are optional. These settings can be changed later, if needed.",
                    type="info",
                ),
                FieldSet(
                    "General",
                    FieldSet.Field(
                        "Storage Profile: ",
                        Select(
                            SplashPageState.storage_profiles,
                            placeholder="Select a storage profile",
                            form=cls.form_id,
                            name="storage_profile",
                            required=True,
                        ),
                    ),
                ),
                FieldSet(
                    "Default Settings",
                    FieldSet.Field(
                        "Proxmox Node: ",
                        Select(
                            rx.Var.create(SplashPageState.nodes).to(list[str]),
                            placeholder="Select Proxmox Node",
                            form=cls.form_id,
                            name="primary_node",
                        ),
                    ),
                    # TODO: Add Storage Defaults
                ),
                id=cls.form_id,
                on_submit=cls.configure_defaults,
            ),
            rx.el.div(
                Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex justify-end mt-4",
            ),
            dialog_id=cls.dialog_id,
        )


class InvalidProxmoxConfigurationDialog(EventGroup):
    """Dialog displayed when Proxmox cluster has an invalid configuration with only 2 nodes."""

    @staticmethod
    @rx.event
    async def retry(_: rx.State) -> FrontendEvents:
        """Retry the OrbitLab initialization process."""
        return [
            Dialog.close(InvalidProxmoxConfigurationDialog.dialog_id),
            SplashPage.initialize_orbitlab,
        ]

    dialog_id: Final = "invalid-proxmox-configuration-dialog"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return Dialog(
            "Invalid Proxmox Cluster State",
            rx.el.div(rx.el.p(SplashPageState.initialization_error)),
            rx.el.div(
                Buttons.Primary("Retry", on_click=cls.retry),
                class_name="w-full flex justify-center items-center mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="w-fit h-fit",
        )


class ConfigureBackplaneDialog(EventGroup):
    """Dialog for configuring the backplane network settings during OrbitLab initialization."""

    @staticmethod
    @rx.event
    async def on_submit(state: SplashPageState, form: dict) -> FrontendEvents:
        """Handle form submission for configuring the backplane network."""
        state.initialization_state = InitializationState.RUNNING
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        cluster_manifest.spec.backplane.cidr_block = IPv4Network(form["cidr_block"])
        cluster_manifest.spec.backplane.controller.asn = int(form["asn"])
        cluster_manifest.save()
        return [
            Dialog.close(ConfigureBackplaneDialog.dialog_id),
            SplashPage.initialize_backplane,
        ]

    dialog_id: Final = "configure-backplane-network-dialog"
    form_id: Final = "configure-backplane-network-form"

    def __new__(cls) -> rx.Component:
        """Create and return the dialog."""
        return Dialog(
            "Configure Backplane Network",
            Callout(
                """OrbitLab requires a unique IPv4 CIDR block and ASN to assign to its Backplane network. Once this is
                configured, it CANNOT be reconfigured. Common default values has been pre-filled for your convenience.
                """,
                type="warning",
            ),
            rx.el.form(
                FieldSet(
                    "Backplane",
                    FieldSet.Field(
                        "CIDR Block: ",
                        Input(
                            default_value=NetworkSettings.BACKPLANE.DEFAULT_CIDR,
                            pattern=NetworkSettings.BACKPLANE.NETWORK_REGEX_PATTERN,
                            form=cls.form_id,
                            name="cidr_block",
                            required=True,
                            error="Must be a valid IPv4 CIDR Block between a /24 and a /8",
                        ),
                    ),
                    FieldSet.Field(
                        "ASN: ",
                        Input(
                            default_value=f"{NetworkSettings.BACKPLANE.ASN}",
                            pattern=r"^(?:6500[1-9]|650[1-9]\d|65[1-4]\d{2}|655[0-2]\d|6553[0-4])$",
                            form=cls.form_id,
                            name="asn",
                            required=True,
                            error="Must be a valid ASN between 65001 and 65534",
                        ),
                    ),
                ),
                id=cls.form_id,
                on_submit=cls.on_submit,
            ),
            rx.el.div(
                Buttons.Primary("Submit", form=cls.form_id),
                class_name="w-full flex justify-end mt-4",
            ),
            dialog_id=cls.dialog_id,
            class_name="w-fit h-fit",
        )


class SplashPage(EventGroup):
    """A splash page component for OrbitLab, displaying animated SVG graphics and initialization text."""

    @staticmethod
    @rx.event(background=True)
    async def initialize_orbitlab(state: SplashPageState) -> FrontendEvents:
        """Initialize OrbitLab by discovering the cluster and configuring nodes."""
        discovery_service = DiscoveryService()
        async with state:
            state.initialization_state = InitializationState.RUNNING
            state.subtitle = "Discovering Cluster..."
        cluster_manifest: ClusterManifest | None = await rx.run_in_thread(discovery_service.discover_cluster)
        if not cluster_manifest:
            # The only reason a manifest wouldn't exist is if there are exactly 2 Proxmox nodes in a cluster
            # which is something OrbitLab won't support as it causes too many problems with quorum witness management.
            async with state:
                state.initialization_state = InitializationState.ABORTED
                state.initialization_error = (
                    "The Proxmox cluster is configured with only 2 active quorum nodes. This is not a supported state "
                    "by OrbitLab. Either install OrbitLab on each node individually or add another node to the cluster "
                    "and retry."
                )
                state.subtitle = "Aborted."
                return Dialog.open(InvalidProxmoxConfigurationDialog.dialog_id)
        for node in cluster_manifest.spec.nodes:
            async with state:
                state.subtitle = f"Configuring {node.name} (this may take a few minutes)..."
            await rx.run_in_thread(discovery_service.NodeManagement(node.name).configure_networking)
        async with state:
            state.initialization_state = InitializationState.BACKPLANE
        return Dialog.open(ConfigureBackplaneDialog.dialog_id)

    @staticmethod
    @rx.event(background=True)
    async def initialize_backplane(state: SplashPageState) -> FrontendEvents:
        """Initialize the backplane network configuration for the cluster."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))

        async with state:
            state.subtitle = "Configuring Backplane..."

        if controller := ProxmoxNetworks().describe_evpn_controller():
            async with state:
                state.initialization_state = InitializationState.ABORTED
                state.initialization_error = (
                    f"An EVPN Controller '{controller.controller}' already exists. "
                    "Only one EVPN controller may exist in Proxmox. Delete the current controller and retry."
                )
            return Dialog.open(InvalidProxmoxConfigurationDialog.dialog_id)
        await rx.run_in_thread(lambda: ProxmoxNetworks().create_backplane(cluster=cluster_manifest))
        async with state:
            state.initialization_state = InitializationState.FINALIZE
            state.nodes = [node.name for node in cluster_manifest.get_nodes()]
        return Dialog.open(ConfigureDefaultsDialog.dialog_id)

    @staticmethod
    @rx.event
    async def check_status(state: SplashPageState) -> FrontendEvents | None:
        """Check the current initialization state and open appropriate dialogs."""
        if state.initialization_state == InitializationState.ABORTED:
            return Dialog.open(InvalidProxmoxConfigurationDialog.dialog_id)
        if state.initialization_state == InitializationState.BACKPLANE:
            return Dialog.open(ConfigureBackplaneDialog.dialog_id)
        if state.initialization_state == InitializationState.FINALIZE:
            return Dialog.open(ConfigureDefaultsDialog.dialog_id)
        return None

    def __new__(cls) -> rx.Component:
        """Create and return the SplashPage."""
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
                rx.match(
                    SplashPageState.initialization_state,
                    (
                        InitializationState.NOT_STARTED,
                        rx.el.div(
                            Buttons.Primary("Initialize", on_click=cls.initialize_orbitlab),
                            class_name=(
                                "w-full flex items-center justify-center mt-6 animate-[fadeInUp_3s_ease-in-out] "
                                "relative z-10"
                            ),
                        ),
                    ),
                    (
                        InitializationState.RUNNING,
                        rx.text(
                            SplashPageState.subtitle,
                            class_name="text-[#36E2F4] text-sm mt-2 fade-subtitle",
                        ),
                    ),
                    (
                        InitializationState.BACKPLANE,
                        rx.fragment(
                            rx.text(
                                SplashPageState.subtitle,
                                class_name="text-[#36E2F4] text-sm mt-2 fade-subtitle",
                            ),
                            rx.el.div(on_mount=cls.check_status),
                        ),
                    ),
                    (
                        InitializationState.FINALIZE,
                        rx.fragment(
                            rx.text(
                                SplashPageState.subtitle,
                                class_name="text-[#36E2F4] text-sm mt-2 fade-subtitle",
                            ),
                            rx.el.div(on_mount=cls.check_status),
                        ),
                    ),
                    (
                        InitializationState.ABORTED,
                        rx.fragment(
                            rx.text(
                                SplashPageState.subtitle,
                                class_name="text-[#36E2F4] text-sm mt-2 fade-subtitle",
                            ),
                            rx.el.div(on_mount=cls.check_status),
                        ),
                    ),
                ),
                class_name="flex flex-col items-center justify-center",
            ),
            InvalidProxmoxConfigurationDialog(),
            ConfigureBackplaneDialog(),
            ConfigureDefaultsDialog(),
            class_name=(
                "relative flex flex-col items-center justify-center min-h-screen w-full "
                "bg-[#0E1015] overflow-hidden select-none"
            ),
        )
