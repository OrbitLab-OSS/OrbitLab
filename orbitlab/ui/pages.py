"""NiceGUI routes for the operator-focused OrbitLab interface.

These pages are intentionally snapshot based.  Operators choose when to
refresh data; workflows persist their job state separately in Activity.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from nicegui import ui

from orbitlab.proxmox import Proxmox
from orbitlab.redis import models
from orbitlab.ui.components import ApplicationShell, DetailView, InventoryTable, PageHeader, StatusBadge
from orbitlab.ui.state import AttentionItem, Clients, ResourceDetail, SummaryCard
from orbitlab.ui.uploads import BuildUploadStore, UploadedBuildFile


def _notify_result(message: str) -> None:
    ui.notify(message, type="positive", position="top")


def _notify_error(error: Exception) -> None:
    ui.notify(str(error), type="negative", position="top")


def _confirm(label: str, action: Callable[[], Awaitable[None]]) -> None:
    """Offer a confirmation for destructive page actions."""
    with ui.dialog() as dialog, ui.card().classes("ol-card w-[420px] p-6"):
        ui.label(label).classes("text-lg font-semibold")
        ui.label("This queues or performs a destructive operation. It cannot be undone from OrbitLab.").classes("ol-muted text-sm")

        async def confirm() -> None:
            try:
                await action()
                dialog.close()
            except Exception as error:  # noqa: BLE001
                _notify_error(error)

        with ui.row().classes("w-full justify-end gap-3 mt-5"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Continue", color="negative", on_click=confirm).props("no-caps")
    ui.button(label, color="negative", icon="delete", on_click=dialog.open).props("outline no-caps")


@dataclass(slots=True)
class OverviewPage:
    """Operator landing page focused on actionability rather than versions."""

    clients: Clients

    @ui.refreshable_method
    async def render(self) -> None:
        """Render an explicit point-in-time lab overview."""
        cards, attention = await self.clients.queries.overview()
        PageHeader("Lab Overview", "A point-in-time view of managed infrastructure.", self.render.refresh).render()
        if not await self.clients.cluster.is_initialized():
            with ui.card().classes("ol-card w-full p-5 mb-6"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("rocket_launch", size="1.5rem").classes("text-[#36E2F4]")
                    with ui.column().classes("gap-0 flex-1"):
                        ui.label("OrbitLab needs initial setup.").classes("font-semibold")
                        ui.label("Choose the Backplane network and PVE storage defaults, then let the worker finish the baseline.").classes("ol-muted text-sm")
                    ui.button("Open setup", icon="arrow_forward", on_click=lambda: ui.navigate.to("/setup")).props("no-caps")
        ui.label("Attention").classes("text-lg font-semibold mb-2")
        if attention:
            for item in attention:
                self._attention(item)
        else:
            with ui.card().classes("ol-card w-full p-5 mb-6"):
                ui.icon("check_circle", size="1.5rem").classes("text-green-400")
                ui.label("Nothing needs attention.").classes("ml-2 inline-block")
        with ui.row().classes("w-full gap-4 flex-wrap"):
            for card in cards:
                self._summary(card)
        with ui.row().classes("w-full gap-3 mt-6"):
            ui.button("Manage Compute", icon="memory", on_click=lambda: ui.navigate.to("/compute")).props("no-caps")
            ui.button("Manage Networks", icon="hub", on_click=lambda: ui.navigate.to("/sectors")).props("outline no-caps")
            ui.button("View Activity", icon="receipt_long", on_click=lambda: ui.navigate.to("/activity")).props("outline no-caps")

    @staticmethod
    def _attention(item: AttentionItem) -> None:
        with ui.card().classes("ol-card w-full p-4 mb-2 cursor-pointer") as card:
            card.on("click", lambda target=item.path: ui.navigate.to(target))
            with ui.row().classes("items-center gap-3"):
                ui.icon("warning", size="1.3rem").classes("text-amber-400" if item.severity == "warning" else "text-red-400")
                with ui.column().classes("gap-0"):
                    ui.label(item.title).classes("font-medium")
                    ui.label(item.detail).classes("ol-muted text-sm")

    @staticmethod
    def _summary(card: SummaryCard) -> None:
        with ui.card().classes("ol-card p-5 min-w-[215px] flex-1 cursor-pointer") as container:
            container.on("click", lambda target=card.path: ui.navigate.to(target))
            ui.label(card.title).classes("ol-muted text-sm font-medium")
            ui.label(card.value).classes("text-2xl font-bold mt-2")
            ui.label(card.detail).classes("ol-muted text-sm mt-1")


@dataclass(slots=True)
class InventoryPage:
    """Reusable collection page with human-readable rows and manual refresh."""

    clients: Clients
    resource: str
    title: str
    subtitle: str
    empty_message: str

    async def render(self) -> None:
        """Compose the page and bind refresh to its table only."""
        table = InventoryTable(
            self.title,
            lambda: self.clients.queries.rows(self.resource),
            self.empty_message,
            open_row=lambda row: ui.navigate.to(row["path"]),
        )
        PageHeader(self.title, self.subtitle, table.render.refresh).render()
        await table.render()


@dataclass(slots=True)
class DetailPage:
    """A manual-refresh detail page for one managed object."""

    clients: Clients
    resource: str
    resource_id: str
    collection_path: str

    @ui.refreshable_method
    async def render(self) -> None:
        """Render resource facts and the constrained actions that apply to it."""
        detail = await self.clients.queries.detail(self.resource, self.resource_id)
        with ui.row().classes("w-full items-center justify-between gap-4 mb-2"):
            with ui.row().classes("items-center gap-3"):
                ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to(self.collection_path)).props("flat round")
                with ui.column().classes("gap-0"):
                    ui.label(detail.title).classes("text-2xl font-bold tracking-tight")
                    ui.label(detail.subtitle).classes("ol-muted text-sm")
            ui.button("Refresh", icon="refresh", on_click=self.render.refresh).props("outline dense no-caps")
        DetailView(detail.status, tuple((section.title, section.values) for section in detail.sections)).render()
        self._actions(detail)

    def _actions(self, detail: ResourceDetail) -> None:
        """Render only actions supported by the durable worker command model."""
        if not detail.actions:
            return
        ui.label("Actions").classes("text-lg font-semibold mt-7 mb-2")
        with ui.row().classes("w-full gap-3 flex-wrap"):
            for action in detail.actions:
                if action == "delete":
                    _confirm("Delete", self._delete)
                elif action == "rotate":
                    self._rotate_secret()
                elif action == "rollback":
                    ui.button("Rollback secret", icon="undo", on_click=self._rollback_secret).props("outline no-caps")
                elif action == "proxmox":
                    ui.button("View in Proxmox", icon="open_in_new", on_click=self._proxmox).props("outline no-caps")
                else:
                    label = action.replace("-", " ").title()
                    ui.button(label, icon="play_arrow", on_click=lambda selected=action: self._run_action(selected)).props("outline no-caps")

    async def _delete(self) -> None:
        job = await self.clients.commands.delete_resource(self.resource, self.resource_id)
        _notify_result(f"Queued {job.name}." if job else "Deleted.")
        if not job:
            ui.navigate.to(self.collection_path)

    async def _run_action(self, action: str) -> None:
        try:
            if self.resource == "compute":
                result = await self.clients.commands.compute_action(action, self.resource_id)
            elif self.resource == "sectors":
                result = await self.clients.commands.sector_action(action, self.resource_id)
            elif self.resource in {"appliances", "images"}:
                result = await self.clients.commands.template_action(self.resource, action, self.resource_id)
            else:
                raise ValueError(f"Action '{action}' is not supported for {self.resource}.")
            _notify_result(f"Queued {result.name}." if hasattr(result, "name") else str(result))
        except Exception as error:  # noqa: BLE001
            _notify_error(error)

    async def _proxmox(self) -> None:
        try:
            result = await self.clients.commands.compute_action("proxmox", self.resource_id)
            ui.navigate.to(str(result), new_tab=True)
        except Exception as error:  # noqa: BLE001
            _notify_error(error)

    async def _rollback_secret(self) -> None:
        try:
            await self.clients.secrets.rollback(self.resource_id)
            _notify_result("Secret rolled back.")
            self.render.refresh()
        except Exception as error:  # noqa: BLE001
            _notify_error(error)

    def _rotate_secret(self) -> None:
        with ui.dialog() as dialog, ui.card().classes("ol-card w-[480px] p-6"):
            ui.label("Rotate secret").classes("text-lg font-semibold")
            value = ui.input("New value", password=True, password_toggle_button=True).classes("w-full")

            async def rotate() -> None:
                try:
                    await self.clients.commands.rotate_secret(name=self.resource_id, value=str(value.value))
                    dialog.close()
                    _notify_result("Secret rotated.")
                    self.render.refresh()
                except Exception as error:  # noqa: BLE001
                    _notify_error(error)

            with ui.row().classes("w-full justify-end gap-3 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                ui.button("Rotate", on_click=rotate).props("no-caps")
        ui.button("Rotate secret", icon="sync", on_click=dialog.open).props("outline no-caps")


@dataclass(slots=True)
class SettingsPage:
    """Low-frequency cluster configuration kept below daily operations."""

    clients: Clients

    def render(self) -> None:
        """Render simple settings with explicit validation and persistence."""
        PageHeader("Settings", "Cluster-wide controls that are not part of daily operations.").render()
        with ui.card().classes("ol-card w-full max-w-2xl p-6"):
            ui.label("Appliances source").classes("text-lg font-semibold")
            ui.label("Choose a Git branch when testing appliance changes. OrbitLab validates its metadata before saving it.").classes("ol-muted text-sm mb-4")
            branch = ui.input("Branch", value="main", placeholder="main").classes("w-full")
            status = ui.label().classes("ol-muted text-sm")

            async def load() -> None:
                branch.value = await self.clients.cluster.get_appliances_branch()

            async def save() -> None:
                try:
                    status.text = "Validating Appliances metadata…"
                    status.classes(replace="ol-muted text-sm")
                    status.text = await self.clients.commands.set_appliances_branch(str(branch.value))
                    status.classes(replace="text-green-400 text-sm")
                except Exception as error:  # noqa: BLE001
                    status.text = str(error)
                    status.classes(replace="text-red-400 text-sm")

            ui.button("Validate and save", icon="check", on_click=save).props("no-caps").classes("mt-4")
            ui.timer(0.1, load, once=True)
        with ui.card().classes("ol-card w-full max-w-2xl p-6 mt-5"):
            ui.label("Infrastructure maintenance").classes("text-lg font-semibold")
            ui.label("These operations are queued durably and appear in Activity. They never depend on a browser connection remaining open.").classes("ol-muted text-sm mb-4")

            async def queue(name: str) -> None:
                try:
                    job = await self.clients.commands.enqueue(name=name, payload={})
                    _notify_result(f"Queued {job.name}.")
                except Exception as error:  # noqa: BLE001
                    _notify_error(error)

            async def download_infrastructure() -> None:
                await queue("infrastructure.download")

            async def upgrade_etcd() -> None:
                await queue("etcd.upgrade")

            async def upgrade_backplane() -> None:
                await queue("infrastructure.upgrade-backplane")

            with ui.row().classes("gap-3 flex-wrap"):
                ui.button("Download infrastructure", icon="download", on_click=download_infrastructure).props("outline no-caps")
                ui.button("Upgrade ETCD", icon="upgrade", on_click=upgrade_etcd).props("outline no-caps")
                ui.button("Upgrade Backplane", icon="upgrade", on_click=upgrade_backplane).props("outline no-caps")


@dataclass(slots=True)
class SetupPage:
    """A focused first-run form whose work survives the browser session."""

    clients: Clients

    def render(self) -> None:
        """Render structured bootstrap controls without exposing raw workflow payloads."""
        PageHeader("Initial setup", "Choose once, review carefully, then let the worker establish OrbitLab's baseline.").render()
        with ui.card().classes("ol-card w-full max-w-3xl p-6"):
            ui.label("Backplane network").classes("text-lg font-semibold")
            ui.label("OrbitLab creates a PVE EVPN/VXLAN Backplane, an internal controller LXC, and a three-member ETCD cluster. The selected CIDR cannot be changed in place.").classes("ol-muted text-sm mb-4")
            cidr = ui.input("IPv4 CIDR", value="100.96.0.0/16", placeholder="100.96.0.0/16").classes("w-full")
            ui.separator().classes("my-5")
            ui.label("Infrastructure placement").classes("text-lg font-semibold")
            ui.label("These are the PVE node and storage IDs OrbitLab will use for its own appliance images and baseline services.").classes("ol-muted text-sm mb-4")
            node = ui.input("Proxmox node", placeholder="pve").classes("w-full")
            with ui.row().classes("w-full gap-4 flex-wrap"):
                vztmpl = ui.input("Container template storage", placeholder="local").classes("flex-1 min-w-[240px]")
                imports = ui.input("Import storage", placeholder="local").classes("flex-1 min-w-[240px]")
                rootdir = ui.input("Container disk storage", placeholder="local-lvm").classes("flex-1 min-w-[240px]")
                images = ui.input("VM disk storage", placeholder="local-lvm").classes("flex-1 min-w-[240px]")
            with ui.expansion("Optional storage defaults", icon="tune").classes("w-full mt-3"):
                snippets = ui.input("Snippet storage").classes("w-full")
                iso = ui.input("ISO storage").classes("w-full")
                backup = ui.input("Backup storage").classes("w-full")
            acknowledged = ui.checkbox("I understand OrbitLab will configure PVE SDN and its own baseline services.").classes("mt-5")
            status = ui.label().classes("ol-muted text-sm mt-3")

            async def initialize() -> None:
                try:
                    job = await self.clients.commands.initialize_orbitlab(
                        backplane_cidr=str(cidr.value),
                        node=str(node.value),
                        vztmpl=str(vztmpl.value),
                        imports=str(imports.value),
                        rootdir=str(rootdir.value),
                        images=str(images.value),
                        snippets=str(snippets.value),
                        iso=str(iso.value),
                        backup=str(backup.value),
                        acknowledged=bool(acknowledged.value),
                    )
                    status.text = f"Queued {job.name}. Follow progress in Activity."
                    status.classes(replace="text-green-400 text-sm mt-3")
                except Exception as error:  # noqa: BLE001
                    status.text = str(error)
                    status.classes(replace="text-red-400 text-sm mt-3")

            ui.button("Initialize OrbitLab", icon="rocket_launch", on_click=initialize).props("no-caps").classes("mt-5")


@dataclass(slots=True)
class ActivityPage:
    """A manual-refresh view of durable work, not a notification feed."""

    clients: Clients

    async def render(self) -> None:
        """Render recent jobs with the user's explicit refresh control."""
        table = InventoryTable("Recent operations", self.clients.queries.jobs, "No OrbitLab operations have been queued.", open_row=lambda row: ui.navigate.to(row["path"]))
        PageHeader("Activity", "Durable job history. Refresh to retrieve the latest state.", table.render.refresh).render()
        await table.render()


@dataclass(slots=True)
class LogsPage:
    """Bounded diagnostics for infrequent investigation."""

    clients: Clients

    @ui.refreshable_method
    async def render(self) -> None:
        """Render a fixed-size, user-requested log snapshot."""
        PageHeader("Logs", "A bounded Redis log snapshot; it does not stream into the browser.", self.render.refresh).render()
        tabs = ui.tabs().classes("w-full")
        workflow = ui.tab("Workflow logs")
        system = ui.tab("System logs")
        with ui.tab_panels(tabs, value=workflow).classes("w-full bg-transparent"):
            with ui.tab_panel(workflow):
                ui.code("\n".join(await self.clients.queries.logs("workflow")) or "No workflow logs.", language="text").classes("w-full")
            with ui.tab_panel(system):
                ui.code("\n".join(await self.clients.queries.logs("system")) or "No system logs.", language="text").classes("w-full")


@dataclass(slots=True)
class SecretsPkiPage:
    """A small launchpad for secret and PKI resources."""

    def render(self) -> None:
        PageHeader("Secrets & PKI", "Credentials, certificates, and keys are intentionally separated from daily infrastructure work.").render()
        destinations = (
            ("Secrets", "Encrypted values and rotation history", "/secrets-pki/secrets", "key"),
            ("Certificate authorities", "Root trust anchors", "/secrets-pki/pki/certificate-authorities", "verified_user"),
            ("Intermediate certificates", "Constrained signing authorities", "/secrets-pki/pki/intermediate-certificates", "account_tree"),
            ("Leaf certificates", "Service TLS certificates", "/secrets-pki/pki/leaf-certificates", "description"),
            ("SSH keys", "Managed public key pairs", "/secrets-pki/ssh-keys", "key"),
        )
        with ui.row().classes("w-full flex-wrap gap-4"):
            for title, detail, path, icon in destinations:
                with ui.card().classes("ol-card p-5 min-w-[260px] flex-1 cursor-pointer") as card:
                    card.on("click", lambda target=path: ui.navigate.to(target))
                    ui.icon(icon, size="1.6rem").classes("text-[#36E2F4]")
                    ui.label(title).classes("text-lg font-semibold mt-3")
                    ui.label(detail).classes("ol-muted text-sm")


def _secret_create_dialog(clients: Clients) -> None:
    with ui.dialog() as dialog, ui.card().classes("ol-card w-[520px] p-6"):
        ui.label("Create secret").classes("text-lg font-semibold")
        name = ui.input("Name", placeholder="/my-service/token").classes("w-full")
        description = ui.input("Description").classes("w-full")
        value = ui.input("Value", password=True, password_toggle_button=True).classes("w-full")

        async def create() -> None:
            try:
                await clients.commands.create_secret(name=str(name.value), value=str(value.value), description=str(description.value))
                dialog.close()
                _notify_result("Secret created.")
            except Exception as error:  # noqa: BLE001
                _notify_error(error)

        with ui.row().classes("w-full justify-end gap-3 mt-4"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Create", on_click=create).props("no-caps")
    ui.button("Create secret", icon="add", on_click=dialog.open).props("no-caps")


def _pki_create_dialog(clients: Clients, kind: str) -> None:
    """Render focused certificate creation forms without exposing private keys."""
    with ui.dialog() as dialog, ui.card().classes("ol-card w-[560px] p-6"):
        ui.label(f"Create {kind.replace('-', ' ')}").classes("text-lg font-semibold capitalize")
        common_name = ui.input("Common name").classes("w-full")
        root = ui.input("Signing root / intermediate", placeholder="Required except for a root CA").classes("w-full")
        constraint = ui.input("Domain constraint", placeholder="example.com").classes("w-full")
        dns_names = ui.input("DNS names", placeholder="app.example.com, api.example.com").classes("w-full")
        ip_addresses = ui.input("IP addresses", placeholder="192.0.2.10, 2001:db8::10").classes("w-full")
        subject_fields = {
            "org": ui.input("Organization", value="OrbitLab").classes("w-full"),
            "org_unit": ui.input("Organizational unit", value="Infrastructure").classes("w-full"),
            "country": ui.input("Country", value="US").classes("w-full"),
            "state_or_province": ui.input("State / province", value="Unknown").classes("w-full"),
            "locality": ui.input("Locality", value="Unknown").classes("w-full"),
        }

        async def create() -> None:
            try:
                common = str(common_name.value).strip()
                if kind == "root certificate authority":
                    subject = models.Subject(
                        common_name=common,
                        org=str(subject_fields["org"].value),
                        org_unit=str(subject_fields["org_unit"].value),
                        country=str(subject_fields["country"].value).upper(),
                        state_or_province=str(subject_fields["state_or_province"].value),
                        locality=str(subject_fields["locality"].value),
                    )
                    await clients.commands.create_certificate_authority(subject)
                elif kind == "intermediate certificate":
                    await clients.commands.create_intermediate_certificate(common, str(root.value).strip(), str(constraint.value).strip())
                else:
                    split = lambda value: [item.strip() for item in str(value).split(",") if item.strip()]
                    await clients.commands.create_leaf_certificate(common, str(root.value).strip(), split(dns_names.value), split(ip_addresses.value))
                dialog.close()
                _notify_result("Certificate created.")
            except Exception as error:  # noqa: BLE001
                _notify_error(error)

        with ui.row().classes("w-full justify-end gap-3 mt-4"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Create", on_click=create).props("no-caps")
    ui.button("Create", icon="add", on_click=dialog.open).props("no-caps")


def _ssh_key_create_dialog(clients: Clients) -> None:
    with ui.dialog() as dialog, ui.card().classes("ol-card w-[460px] p-6"):
        ui.label("Create SSH key pair").classes("text-lg font-semibold")
        name = ui.input("Name").classes("w-full")
        key_type = ui.select({"ed25519": "Ed25519", "rsa": "RSA"}, value="ed25519", label="Type").classes("w-full")

        async def create() -> None:
            try:
                await clients.commands.create_ssh_key(str(name.value), str(key_type.value))
                dialog.close()
                _notify_result("SSH key pair created.")
            except Exception as error:  # noqa: BLE001
                _notify_error(error)

        with ui.row().classes("w-full justify-end gap-3 mt-4"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Create", on_click=create).props("no-caps")
    ui.button("Create SSH key", icon="add", on_click=dialog.open).props("no-caps")


def _compute_create_dialog(clients: Clients) -> None:
    """Create a focused compute manifest, leaving Proxmox work to the worker."""
    with ui.dialog() as dialog, ui.card().classes("ol-card w-[620px] p-6"):
        ui.label("Create compute").classes("text-lg font-semibold")
        ui.label("Use an existing appliance for LXC or image for VM. The worker allocates the VMID only when it creates the guest.").classes("ol-muted text-sm")
        instance_type = ui.select({"lxc": "LXC", "qemu": "VM"}, value="lxc", label="Type").classes("w-full")
        name = ui.input("Name").classes("w-full")
        source = ui.input("Appliance / image ID").classes("w-full")
        with ui.row().classes("w-full gap-4"):
            node = ui.input("Proxmox node").classes("flex-1")
            sector = ui.input("Sector ID").classes("flex-1")
            storage = ui.input("Storage").classes("flex-1")
        with ui.row().classes("w-full gap-4"):
            disk = ui.number("Disk (GiB)", value=16, min=1).classes("flex-1")
            memory = ui.number("Memory (MiB)", value=2048, min=256).classes("flex-1")
            cores = ui.number("Cores", value=2, min=1).classes("flex-1")
        password = ui.input("Initial password (optional)", password=True, password_toggle_button=True).classes("w-full")

        async def create() -> None:
            try:
                job = await clients.commands.create_compute(
                    instance_type=str(instance_type.value), name=str(name.value), source_id=str(source.value),
                    node=str(node.value), storage=str(storage.value), sector_id=str(sector.value),
                    disk_size=int(disk.value), memory=int(memory.value), cores=int(cores.value), password=str(password.value),
                )
                dialog.close()
                _notify_result(f"Queued {job.name}.")
            except Exception as error:  # noqa: BLE001
                _notify_error(error)

        with ui.row().classes("w-full justify-end gap-3 mt-4"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Create", on_click=create).props("no-caps")
    ui.button("Create compute", icon="add", on_click=dialog.open).props("no-caps")


def _sector_create_dialog(clients: Clients) -> None:
    with ui.dialog() as dialog, ui.card().classes("ol-card w-[520px] p-6"):
        ui.label("Create sector").classes("text-lg font-semibold")
        ui.label("OrbitLab assigns the VLAN and backplane address. Enter an unused private CIDR.").classes("ol-muted text-sm")
        alias = ui.input("Name", placeholder="Media services").classes("w-full")
        cidr = ui.input("CIDR", placeholder="10.42.0.0/24").classes("w-full")
        storage = ui.input("Storage").classes("w-full")

        async def create() -> None:
            try:
                job = await clients.commands.create_sector(alias=str(alias.value), cidr_block=str(cidr.value), storage=str(storage.value))
                dialog.close()
                _notify_result(f"Queued {job.name}.")
            except Exception as error:  # noqa: BLE001
                _notify_error(error)

        with ui.row().classes("w-full justify-end gap-3 mt-4"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Create", on_click=create).props("no-caps")
    ui.button("Create sector", icon="add", on_click=dialog.open).props("no-caps")


def _datacore_create_dialog(clients: Clients) -> None:
    with ui.dialog() as dialog, ui.card().classes("ol-card w-[580px] p-6"):
        ui.label("Create DataCore").classes("text-lg font-semibold")
        name = ui.input("Name").classes("w-full")
        with ui.row().classes("w-full gap-4"):
            sector = ui.input("Sector ID").classes("flex-1")
            storage = ui.input("Storage").classes("flex-1")
        with ui.row().classes("w-full gap-4"):
            replicas = ui.number("Replicas", value=2, min=0).classes("flex-1")
            memory = ui.number("Memory per member (GiB)", value=2, min=1).classes("flex-1")
            cores = ui.number("Cores per member", value=2, min=1).classes("flex-1")
            capacity = ui.number("Capacity (GiB)", value=20, min=1).classes("flex-1")

        async def create() -> None:
            try:
                job = await clients.commands.create_datacore(
                    name=str(name.value), sector_id=str(sector.value), storage=str(storage.value), replicas=int(replicas.value),
                    memory_gb=int(memory.value), cores=int(cores.value), capacity_gb=int(capacity.value),
                )
                dialog.close()
                _notify_result(f"Queued {job.name}.")
            except Exception as error:  # noqa: BLE001
                _notify_error(error)

        with ui.row().classes("w-full justify-end gap-3 mt-4"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Create", on_click=create).props("no-caps")
    ui.button("Create DataCore", icon="add", on_click=dialog.open).props("no-caps")


def _dockfs_create_dialog(clients: Clients) -> None:
    with ui.dialog() as dialog, ui.card().classes("ol-card w-[580px] p-6"):
        ui.label("Create DockFS").classes("text-lg font-semibold")
        name = ui.input("Name").classes("w-full")
        with ui.row().classes("w-full gap-4"):
            sector = ui.input("Sector ID").classes("flex-1")
            storage = ui.input("Storage").classes("flex-1")
        with ui.row().classes("w-full gap-4"):
            capacity = ui.number("Capacity (GiB)", value=100, min=1).classes("flex-1")
            memory = ui.number("Memory per node (GiB)", value=2, min=1).classes("flex-1")
            cores = ui.number("Cores per node", value=2, min=1).classes("flex-1")
            sockets = ui.number("Sockets per node", value=1, min=1).classes("flex-1")

        async def create() -> None:
            try:
                job = await clients.commands.create_dockfs(
                    name=str(name.value), sector_id=str(sector.value), storage=str(storage.value), capacity_gb=int(capacity.value),
                    memory=int(memory.value), cores=int(cores.value), sockets=int(sockets.value),
                )
                dialog.close()
                _notify_result(f"Queued {job.name}.")
            except Exception as error:  # noqa: BLE001
                _notify_error(error)

        with ui.row().classes("w-full justify-end gap-3 mt-4"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Create", on_click=create).props("no-caps")
    ui.button("Create DockFS", icon="add", on_click=dialog.open).props("no-caps")


def _conduit_pool_create_dialog(clients: Clients) -> None:
    with ui.dialog() as dialog, ui.card().classes("ol-card w-[560px] p-6"):
        ui.label("Create Conduit pool").classes("text-lg font-semibold")
        ui.label("Pools route traffic to managed compute in one sector. Enter target IDs as a comma-separated list.").classes("ol-muted text-sm")
        name = ui.input("Name").classes("w-full")
        sector = ui.input("Sector ID").classes("w-full")
        targets = ui.input("Compute target IDs", placeholder="ovi123, ovi456").classes("w-full")
        with ui.row().classes("w-full gap-4"):
            port = ui.number("Service port", value=80, min=1, max=65535).classes("flex-1")
            balance = ui.select({"roundrobin": "Round robin", "leastconn": "Least connections"}, value="roundrobin", label="Balancing").classes("flex-1")

        async def create() -> None:
            try:
                target_ids = [item.strip() for item in str(targets.value).split(",") if item.strip()]
                job = await clients.commands.create_conduit_pool(name=str(name.value), sector_id=str(sector.value), target_ids=target_ids, port=int(port.value), balance=str(balance.value))
                dialog.close()
                _notify_result(f"Queued {job.name}.")
            except Exception as error:  # noqa: BLE001
                _notify_error(error)

        with ui.row().classes("w-full justify-end gap-3 mt-4"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Create", on_click=create).props("no-caps")
    ui.button("Create pool", icon="add", on_click=dialog.open).props("no-caps")


def _conduit_endpoint_create_dialog(clients: Clients) -> None:
    with ui.dialog() as dialog, ui.card().classes("ol-card w-[540px] p-6"):
        ui.label("Publish Conduit endpoint").classes("text-lg font-semibold")
        ui.label("Each endpoint publishes a domain through an existing pool in the same sector.").classes("ol-muted text-sm")
        name = ui.input("Name").classes("w-full")
        domain = ui.input("Domain", placeholder="service.example.com").classes("w-full")
        with ui.row().classes("w-full gap-4"):
            sector = ui.input("Sector ID").classes("flex-1")
            pool = ui.input("Pool ID").classes("flex-1")
        endpoint_type = ui.select({"http": "HTTP", "https": "HTTPS"}, value="https", label="Type").classes("w-full")

        async def create() -> None:
            try:
                job = await clients.commands.create_conduit_endpoint(name=str(name.value), domain=str(domain.value), sector_id=str(sector.value), pool_id=str(pool.value), endpoint_type=str(endpoint_type.value))
                dialog.close()
                _notify_result(f"Queued {job.name}.")
            except Exception as error:  # noqa: BLE001
                _notify_error(error)

        with ui.row().classes("w-full justify-end gap-3 mt-4"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Create", on_click=create).props("no-caps")
    ui.button("Publish endpoint", icon="add", on_click=dialog.open).props("no-caps")


def _custom_template_create_dialog(clients: Clients, template_kind: str) -> None:
    """Create custom templates with an optional readable bootstrap script."""
    is_appliance = template_kind == "appliance"
    uploads = BuildUploadStore()
    uploaded_files: list[UploadedBuildFile] = []
    with ui.dialog() as dialog, ui.card().classes("ol-card w-[640px] p-6"):
        ui.label(f"Create custom {template_kind}").classes("text-lg font-semibold capitalize")
        ui.label("The build runs as a durable worker job. An optional shell script is run during image construction.").classes("ol-muted text-sm")
        name = ui.input("Name").classes("w-full")
        base = ui.input(f"Base {template_kind} ID").classes("w-full")
        with ui.row().classes("w-full gap-4"):
            node = ui.input("Proxmox node").classes("flex-1")
            sector = ui.input("Sector ID").classes("flex-1")
        with ui.row().classes("w-full gap-4"):
            disk_store = ui.input("Build disk storage").classes("flex-1")
            output_store = ui.input("Output storage").classes("flex-1")
        with ui.row().classes("w-full gap-4"):
            disk_size = ui.number("Disk size (GiB)", value=16, min=1).classes("flex-1")
            memory = ui.number("Memory (GiB)", value=2, min=1).classes("flex-1")
            cores = ui.number("Cores", value=2, min=1).classes("flex-1")
        swap = ui.number("Swap (GiB)", value=1, min=0).classes("w-full") if is_appliance else None
        script = ui.textarea("Configuration script (optional)", placeholder="apt-get update\napt-get install -y ...").classes("w-full")
        with ui.expansion("Copy files into the build (optional)", icon="upload_file").classes("w-full"):
            ui.label("Upload files, then choose the absolute guest path for each one. Files remain on the OrbitLab host only for this build.").classes("ol-muted text-sm mb-2")
            destinations = ui.column().classes("w-full gap-2")

            async def upload_file(event: object) -> None:
                try:
                    uploaded = await uploads.save(event)
                    uploaded_files.append(uploaded)
                    with destinations:
                        destination = ui.input(
                            f"{uploaded.filename} destination",
                            value=str(uploaded.destination),
                        ).classes("w-full")
                        destination.on_value_change(lambda change, target=uploaded: setattr(target, "destination", Path(str(change.value))))
                except Exception as error:  # noqa: BLE001
                    _notify_error(error)

            ui.upload(on_upload=upload_file, auto_upload=True, multiple=True).props("accept=* max-files=20").classes("w-full")

        async def create() -> None:
            try:
                if is_appliance:
                    job = await clients.commands.create_custom_appliance(
                        name=str(name.value), base_id=str(base.value), node=str(node.value), sector_id=str(sector.value),
                        disk_store=str(disk_store.value), storage=str(output_store.value), cores=int(cores.value),
                        memory=int(memory.value), swap=int(swap.value) if swap else 0, script=str(script.value),
                        files=[uploaded.as_workflow_file() for uploaded in uploaded_files],
                    )
                else:
                    job = await clients.commands.create_custom_image(
                        name=str(name.value), base_id=str(base.value), node=str(node.value), sector_id=str(sector.value),
                        disk_storage=str(disk_store.value), storage=str(output_store.value), disk_size=int(disk_size.value),
                        cores=int(cores.value), memory=int(memory.value), script=str(script.value),
                        files=[uploaded.as_workflow_file() for uploaded in uploaded_files],
                    )
                dialog.close()
                _notify_result(f"Queued {job.name}.")
            except Exception as error:  # noqa: BLE001
                _notify_error(error)

        with ui.row().classes("w-full justify-end gap-3 mt-4"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Create", on_click=create).props("no-caps")
    ui.button(f"Create custom {template_kind}", icon="add", on_click=dialog.open).props("no-caps")


def register_routes(clients: Clients) -> None:
    """Register the complete NiceGUI operator surface once at startup."""
    @ui.page("/")
    async def home() -> None:
        with ApplicationShell("/").content():
            await OverviewPage(clients).render()

    @ui.page("/setup")
    async def setup() -> None:
        with ApplicationShell("/setup").content():
            SetupPage(clients).render()

    def register_inventory(path: str, resource: str, title: str, subtitle: str, empty_message: str) -> None:
        @ui.page(path)
        async def page() -> None:
            with ApplicationShell(path).content():
                await InventoryPage(clients, resource, title, subtitle, empty_message).render()

    def register_detail(path: str, resource: str, collection_path: str) -> None:
        @ui.page(path)
        async def page(resource_id: str) -> None:
            with ApplicationShell(collection_path).content():
                await DetailPage(clients, resource, resource_id, collection_path).render()

    register_inventory("/nodes", "nodes", "Proxmox Nodes", "Host health and placement at a glance.", "No Proxmox nodes are registered yet.")
    register_detail("/nodes/{resource_id}", "nodes", "/nodes")

    @ui.page("/compute")
    async def compute() -> None:
        with ApplicationShell("/compute").content():
            _compute_create_dialog(clients)
            await InventoryPage(clients, "compute", "Compute", "Managed VMs and LXCs. Open a resource for controls and runtime state.", "No managed compute instances exist.").render()

    register_detail("/compute/{resource_id}", "compute", "/compute")
    @ui.page("/compute/appliances")
    async def appliances() -> None:
        with ApplicationShell("/compute/appliances").content():
            _custom_template_create_dialog(clients, "appliance")
            await InventoryPage(clients, "appliances", "Appliances", "Base and custom LXC templates used to build infrastructure and services.", "No appliance templates are registered.").render()

    register_detail("/appliances/{resource_id}", "appliances", "/compute/appliances")
    @ui.page("/compute/images")
    async def images() -> None:
        with ApplicationShell("/compute/appliances").content():
            _custom_template_create_dialog(clients, "image")
            await InventoryPage(clients, "images", "Images", "Base and custom VM images used by managed compute.", "No VM images are registered.").render()

    register_detail("/images/{resource_id}", "images", "/compute/images")
    @ui.page("/sectors")
    async def sectors() -> None:
        with ApplicationShell("/sectors").content():
            _sector_create_dialog(clients)
            await InventoryPage(clients, "sectors", "Sectors", "Isolated networks, gateways, DNS, and ingress capabilities.", "No sectors have been created.").render()

    register_detail("/sectors/{resource_id}", "sectors", "/sectors")
    @ui.page("/datacore")
    async def datacore() -> None:
        with ApplicationShell("/datacore").content():
            _datacore_create_dialog(clients)
            await InventoryPage(clients, "datacore", "DataCore", "Database clusters and their primary/replica health.", "No DataCore clusters exist.").render()

    register_detail("/datacore/{resource_id}", "datacore", "/datacore")
    @ui.page("/dock-fs")
    async def dockfs() -> None:
        with ApplicationShell("/dock-fs").content():
            _dockfs_create_dialog(clients)
            await InventoryPage(clients, "dock-fs", "DockFS", "Managed storage clusters and their active export endpoint.", "No DockFS clusters exist.").render()

    register_detail("/dock-fs/{resource_id}", "dock-fs", "/dock-fs")
    @ui.page("/conduit")
    async def conduit() -> None:
        with ApplicationShell("/conduit").content():
            with ui.row().classes("w-full gap-3"):
                _conduit_endpoint_create_dialog(clients)
                ui.button("Manage pools", icon="account_tree", on_click=lambda: ui.navigate.to("/conduit/pools")).props("outline no-caps")
            await InventoryPage(clients, "conduit", "Conduit", "Published endpoints are shown before their backing pools.", "No Conduit endpoints are configured.").render()

    register_detail("/conduit/{resource_id}", "conduit", "/conduit")
    @ui.page("/conduit/pools")
    async def conduit_pools() -> None:
        with ApplicationShell("/conduit").content():
            _conduit_pool_create_dialog(clients)
            await InventoryPage(clients, "conduit-pools", "Conduit pools", "Backends and health checks for published endpoints.", "No Conduit pools are configured.").render()

    register_detail("/conduit/pools/{resource_id}", "conduit-pools", "/conduit/pools")

    @ui.page("/compute/autoscaling")
    async def autoscaling() -> None:
        with ApplicationShell("/compute").content():
            PageHeader("Autoscaling", "Autoscaling remains unavailable until its worker contract is implemented; no incomplete controls are exposed.").render()
            with ui.card().classes("ol-card w-full max-w-2xl p-6"):
                ui.icon("construction", size="2rem").classes("text-amber-400")
                ui.label("Autoscaling is not configured.").classes("text-lg font-semibold mt-3")
                ui.label("OrbitLab will expose this page once a durable autoscaling worker owns desired count and recovery behavior.").classes("ol-muted text-sm")

    @ui.page("/secrets-pki")
    async def secrets_pki() -> None:
        with ApplicationShell("/secrets-pki").content():
            SecretsPkiPage().render()

    def register_secret_inventory(path: str, resource: str, title: str, subtitle: str, empty: str, create: Callable[[], None]) -> None:
        @ui.page(path)
        async def page() -> None:
            with ApplicationShell("/secrets-pki").content():
                create()
                await InventoryPage(clients, resource, title, subtitle, empty).render()

    register_secret_inventory("/secrets-pki/secrets", "secrets", "Secrets", "Encrypted values. Secret material is never rendered in the browser.", "No user-managed secrets exist.", lambda: _secret_create_dialog(clients))
    register_detail("/secrets-pki/secrets/{resource_id:path}", "secrets", "/secrets-pki/secrets")
    register_secret_inventory("/secrets-pki/pki/certificate-authorities", "root-certificates", "Certificate authorities", "Root trust anchors for the lab.", "No root certificate authorities exist.", lambda: _pki_create_dialog(clients, "root certificate authority"))
    register_detail("/secrets-pki/pki/root-certificates/{resource_id}", "root-certificates", "/secrets-pki/pki/certificate-authorities")
    register_secret_inventory("/secrets-pki/pki/intermediate-certificates", "intermediate-certificates", "Intermediate certificates", "Constrained signing authorities.", "No intermediate certificates exist.", lambda: _pki_create_dialog(clients, "intermediate certificate"))
    register_detail("/secrets-pki/pki/intermediate-certificates/{resource_id}", "intermediate-certificates", "/secrets-pki/pki/intermediate-certificates")
    register_secret_inventory("/secrets-pki/pki/leaf-certificates", "leaf-certificates", "Leaf certificates", "Service certificates and expiration state.", "No leaf certificates exist.", lambda: _pki_create_dialog(clients, "leaf certificate"))
    register_detail("/secrets-pki/pki/leaf-certificates/{resource_id}", "leaf-certificates", "/secrets-pki/pki/leaf-certificates")
    register_secret_inventory("/secrets-pki/ssh-keys", "ssh-keys", "SSH keys", "Managed key pairs. Private keys remain in the encrypted vault.", "No SSH key pairs exist.", lambda: _ssh_key_create_dialog(clients))
    register_detail("/secrets-pki/ssh-keys/{resource_id}", "ssh-keys", "/secrets-pki/ssh-keys")

    @ui.page("/activity")
    async def activity() -> None:
        with ApplicationShell("/activity").content():
            await ActivityPage(clients).render()

    @ui.page("/activity/{resource_id}")
    async def activity_detail(resource_id: str) -> None:
        with ApplicationShell("/activity").content():
            detail = await clients.queries.job(resource_id)
            PageHeader(detail.title, detail.subtitle).render()
            DetailView(detail.status, tuple((section.title, section.values) for section in detail.sections)).render()

    @ui.page("/logs")
    async def logs() -> None:
        with ApplicationShell("/activity").content():
            await LogsPage(clients).render()

    @ui.page("/settings")
    async def settings() -> None:
        with ApplicationShell("/settings").content():
            SettingsPage(clients).render()

    @ui.page("/terminal/{vmid}")
    async def terminal(vmid: str) -> None:
        with ApplicationShell("/compute").content():
            PageHeader("Console", f"VMID {vmid}").render()
            with ui.card().classes("ol-card max-w-2xl p-6"):
                ui.label("Use the Proxmox console for interactive sessions.").classes("text-lg font-semibold")
                ui.label("OrbitLab no longer hosts a separate Reflex WebSocket proxy. This keeps credentials and terminal transport inside the Proxmox control plane.").classes("ol-muted text-sm mb-4")
                try:
                    resource = await Proxmox().get_compute_resource(int(vmid))
                    ui.link("Open console in Proxmox", await Proxmox().get_view_in_proxmox_url(vmid=int(vmid), compute_type=resource.type), new_tab=True).classes("text-[#7DECF8]")
                except Exception as error:  # noqa: BLE001
                    ui.label(f"Unable to resolve this VMID: {error}").classes("text-red-400")
