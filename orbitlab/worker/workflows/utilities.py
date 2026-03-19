"""OrbitLab Workflow Utilities."""

import asyncio
import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from functools import cached_property
from ipaddress import IPv4Address, IPv4Interface
import re
from string import Template
from typing import Any, Literal

import backoff
import httpx
import reflex as rx
from redis.asyncio import Redis
from reflex.utils.prerequisites import get_app

from orbitlab.data_types import ComputeState, ComputeStatus, OrbitLabApplianceType, StorageContentType
from orbitlab.manifest.cluster import ClusterManifest, ETCDMember, InfraAppliance
from orbitlab.manifest.compute_templates.workflow_models import File, ScriptStep
from orbitlab.manifest.dockfs import DockFsHost
from orbitlab.manifest.pki import IntermediateCertificateManifest, LeafCertificateManifest, RootCertificateManifest
from orbitlab.manifest.secrets import SecretManifest
from orbitlab.manifest.sector import SectorManifest
from orbitlab.proxmox import Proxmox, ProxmoxCompute, ProxmoxComputeTemplates, ProxmoxNetworks
from orbitlab.proxmox.base.models import Task
from orbitlab.proxmox.compute.models import LXCInterfaces, QemuConfig, VMInterfaces, VendoredImage
from orbitlab.proxmox.compute_templates.models import AgentExecPid, AgentExecStatus, OrbitLabAppliance, VolumeContentInfo
from orbitlab.services.pki.client import Certificates
from orbitlab.web.pages.compute.lxc.instances.states import LXCInstancesTableState
from orbitlab.worker.events import WorkflowEvent

type EventReturn = rx.event.EventHandler | rx.event.EventSpec | list[rx.event.EventHandler | rx.event.EventSpec]
type RecordType = Literal["internal", "external"]
type DockFSNodeType = Literal["active", "passive"]


class _Util:
    event: WorkflowEvent
    redis: Redis

    @cached_property
    def proxmox(self) -> Proxmox:
        """Get the Proxmox client instance."""
        return Proxmox()

    def _redact_params(self, params: dict) -> dict:
        redactable = ("cipassword", "password", "ssh-public-keys")
        return {k: "*****" if k in redactable else v for k, v in params.items()}

    async def run_sync(self, func: Callable, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return await asyncio.get_event_loop().run_in_executor(executor=None, func=lambda: func(*args, **kwargs))

    async def log(self, message: str, level: Literal["Info", "Warning", "Error"] = "Info") -> None:
        """Log a message with a specified level and message content."""
        print(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": level,
                "workflow": self.event.workflow_id,
                "message": message,
            },
        )

    async def emit_reflex_events(self, events: EventReturn) -> None:
        """Emit events from any async function, not necessarily an event handler."""
        events_to_fix = [events] if not isinstance(events, Sequence) else events

        app: rx.App = get_app().app
        async for token in app.event_namespace._token_manager.enumerate_tokens():  # noqa: SLF001
            await app.event_namespace.emit_update(
                update=rx.state.StateUpdate(
                    events=rx.event.fix_events(
                        events=[e for e in events_to_fix if isinstance(e, rx.event.EventHandler | rx.event.EventSpec)],
                        token=token,
                        router_data={"token": token},
                    ),
                    final=None,
                ),
                token=token,
            )

    async def get_available_vmids(self, count: int) -> list[int]:
        await self.log(f"Getting the next {count} available VMIDs")
        initial = self.proxmox.get_next_vmid()
        vmids = [initial]
        next_id = initial
        while len(vmids) < count:
            next_id += 1
            vmid = self.proxmox.get_next_vmid(vmid=next_id)
            if vmid > 0:
                vmids.append(vmid)
        await self.log(f"The next {count} available VMIDs: {vmids}")
        return vmids


class VMUtils(_Util):
    """Utility class for virtual machine operations."""

    @cached_property
    def proxmox_compute(self) -> ProxmoxCompute:
        """Get the Proxmox compute client instance."""
        return ProxmoxCompute()

    async def create(self, params: dict, *, node: str = "", disk_size: int = 0) -> None:
        """Create a virtual machine (VM) on the specified Proxmox node with the given parameters."""
        vmid = params["vmid"]

        if not node:
            node = self.proxmox_compute.__node__

        await self.log(message=f"Creating {vmid}@{node} with params: {self._redact_params(params=params)}")
        task = self.proxmox_compute.create(path=f"/nodes/{node}/qemu", model=Task, **params)
        await self.run_sync(self.proxmox_compute.wait_for_task, task=task)

        if disk_size:
            await self.log(message=f"Resizing scsi0 on {vmid}@{node} to: {disk_size}G")
            resize_pararms = {"disk": "scsi0", "size": f"{disk_size}G"}
            await asyncio.sleep(1)  # Take a beat so Proxmox doesn't panic when trying to resize the disk after creation
            task = self.proxmox_compute.set(f"/nodes/{node}/qemu/{vmid}/resize", model=Task, **resize_pararms)
            await self.run_sync(self.proxmox_compute.wait_for_task, task=task)

    async def wait_for_agent(self, vmid: int) -> None:
        """Wait for the guest agent on a virtual machine to become available."""
        node = self.proxmox_compute.get_node_for_vmid(vmid=vmid)
        async with asyncio.timeout(30):
            while True:
                try:
                    self.proxmox_compute.create(path=f"/nodes/{node}/qemu/{vmid}/agent/ping", model=None)
                except httpx.HTTPStatusError:
                    await self.log(message=f"Waiting for agent on {vmid}@{node}...")
                    await asyncio.sleep(2)
                else:
                    await self.log(message=f"Agent {vmid}@{node} alive.")
                    break

    async def agent_exec(self, vmid: int, command: list[str]) -> AgentExecStatus:
        """Execute a command on a virtual machine agent and return the execution status."""
        node = self.proxmox_compute.get_node_for_vmid(vmid=vmid)
        await self.log(message=f"On {vmid}@{node} running command: {command}")
        pid_response = self.proxmox_compute.create(
            path=f"/nodes/{node}/qemu/{vmid}/agent/exec",
            model=AgentExecPid,
            command=command,
        )
        status = self.proxmox_compute.get(
            path=f"/nodes/{node}/qemu/{vmid}/agent/exec-status",
            model=AgentExecStatus,
            pid=pid_response.pid,
        )
        while not status.exited:
            await self.log(message=f"Waiting on {vmid}@{node} agent PID {pid_response.pid}")
            await asyncio.sleep(2)
            status = self.proxmox_compute.get(
                path=f"/nodes/{node}/qemu/{vmid}/agent/exec-status",
                model=AgentExecStatus,
                pid=pid_response.pid,
            )
        await self.log(message=f"Agent {vmid}@{node} PID {pid_response.pid} exit code: {status.exitcode}")
        return status

    async def start(self, vmid: int) -> None:
        """Start a virtual machine."""
        if self.proxmox_compute.get_vm_status(vmid=vmid) == "running":
            await self.log(message=f"VM {vmid} already running")
            return

        node = self.proxmox_compute.get_node_for_vmid(vmid=vmid)
        await self.log(message=f"Starting {vmid}@{node}")
        task = self.proxmox_compute.create(path=f"/nodes/{node}/qemu/{vmid}/status/start", model=Task)
        await self.run_sync(self.proxmox_compute.wait_for_task, task=task)

    async def reboot(self, vmid: int) -> None:
        """Reboot a virtual machine or start it if not running."""
        node = self.proxmox_compute.get_node_for_vmid(vmid=vmid)
        if not node:
            await self.log(f"VMID {vmid} not found in Proxmox.")
            return
        if self.proxmox_compute.get_vm_status(vmid=vmid) == "running":
            await self.log(f"Rebooting VMID {vmid} on node {node}")
            task = self.proxmox_compute.create(path=f"/nodes/{node}/qemu/{vmid}/status/reboot", model=Task)
            await self.run_sync(self.proxmox_compute.wait_for_task, task=task)
        else:
            await self.start(vmid=vmid)

    async def stop(self, vmid: int, *, shutdown: bool = False) -> None:
        """Stop a running virtual machine or shutdown gracefully if specified."""
        node = self.proxmox_compute.get_node_for_vmid(vmid=vmid)
        if not node:
            await self.log(f"VMID {vmid} not found in Proxmox.")
            return
        if self.proxmox_compute.get_vm_status(vmid=vmid) == "running":
            status = "shutdown" if shutdown else "stop"
            await self.log(f"Setting VMID {vmid} on node {node} to {status}")
            task = self.proxmox_compute.create(path=f"/nodes/{node}/qemu/{vmid}/status/{status}", model=Task)
            await self.run_sync(self.proxmox_compute.wait_for_task, task=task)
        else:
            await self.log(f"VMID {vmid} on node {node} already stopped.")

    async def terminate(self, vmid: int) -> None:
        """Terminate a virtual machine."""
        node = self.proxmox_compute.get_node_for_vmid(vmid=vmid)
        if not node:
            await self.log(f"VMID {vmid} not found in Proxmox.")
            return

        await self.stop(vmid=vmid)
        params = {"destroy-unreferenced-disks": 1, "purge": 1}
        await self.log(message=f"Terminating VMID {vmid} on node {node}")
        task = self.proxmox_compute.delete(path=f"/nodes/{node}/qemu/{vmid}", model=Task, **params)
        await self.run_sync(self.proxmox_compute.wait_for_task, task=task)

    async def agent_enabled(self, vmid: int) -> bool:
        """Check if the guest agent is enabled on a virtual machine."""
        node = self.proxmox_compute.get_node_for_vmid(vmid=int(vmid))
        config = self.proxmox_compute.get(f"/nodes/{node}/qemu/{vmid}/config", model=QemuConfig)
        return config.agent_enabled

    @backoff.on_predicate(backoff.fibo, max_value=13, max_tries=3)
    async def get_ipv4_address(self, vmid: int) -> IPv4Interface | None:
        """Retrieve the private IPv4 address for the given LXC VMID."""
        node = self.proxmox_compute.get_node_for_vmid(vmid=vmid)
        try:
            interfaces = self.proxmox_compute.get(
                path=f"/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces",
                model=VMInterfaces,
            )
        except httpx.HTTPStatusError:
            return None
        return interfaces.get_default_ipv4()

    async def update_state(self, name: str, status: ComputeStatus, *, vmid: int = 0) -> None:
        """Update the compute state in Redis based on the LXC status or provided status."""
        if vmid:
            final_status = self.proxmox_compute.get_vm_status(vmid=vmid)
            await self.redis.hset(
                name=name,
                key="state",
                value=ComputeState.RUNNING.value if final_status == "running" else ComputeState.STOPPED.value,
            )  # pyright: ignore[reportGeneralTypeIssues]
        else:
            await self.redis.hset(name=name, key="state", value=ComputeStatus.get_state(status=status).value)  # pyright: ignore[reportGeneralTypeIssues]
        await self.emit_reflex_events(events=[LXCInstancesTableState.cache_clear("running")])


class LXCUtils(_Util):
    """Utility class for LXC container operations."""

    @cached_property
    def proxmox_compute(self) -> ProxmoxCompute:
        """Get the Proxmox compute client instance."""
        return ProxmoxCompute()

    async def create(self, params: dict, *, node: str = "") -> None:
        """Create an LXC container on the specified Proxmox node with the given parameters."""
        vmid = params["vmid"]

        if not node:
            node = self.proxmox_compute.__node__

        await self.log(message=f"Creating {vmid}@{node} with params: {self._redact_params(params=params)}")
        task = self.proxmox_compute.create(path=f"/nodes/{node}/lxc", model=Task, **params)
        await self.run_sync(self.proxmox_compute.wait_for_task, task=task)

    @backoff.on_predicate(backoff.fibo, max_value=13, max_tries=5)
    async def get_ipv4_address(self, vmid: int) -> IPv4Interface | None:
        """Retrieve the private IPv4 address for the given LXC VMID."""
        node = self.proxmox_compute.get_node_for_vmid(vmid=vmid)
        interfaces = self.proxmox_compute.get(f"/nodes/{node}/lxc/{vmid}/interfaces", model=LXCInterfaces)
        return interfaces.get_default_ipv4()

    async def start(self, vmid: int) -> None:
        """Start an LXC container."""
        if self.proxmox_compute.get_lxc_status(vmid=vmid) == "running":
            await self.log(message=f"LXC {vmid} already running")
            return
        node = self.proxmox_compute.get_node_for_vmid(vmid=vmid)
        await self.log(message=f"Starting {vmid}@{node}")
        task = self.proxmox_compute.create(path=f"/nodes/{node}/lxc/{vmid}/status/start", model=Task)
        await self.run_sync(self.proxmox_compute.wait_for_task, task=task)

    async def reboot(self, vmid: int) -> None:
        """Reboot an LXC container or start it if not running."""
        node = self.proxmox_compute.get_node_for_vmid(vmid=vmid)
        if not node:
            await self.log(f"VMID {vmid} not found in Proxmox.")
            return
        if self.proxmox_compute.get_lxc_status(vmid=vmid) == "running":
            await self.log(f"Rebooting VMID {vmid} on node {node}")
            task = self.proxmox_compute.create(path=f"/nodes/{node}/lxc/{vmid}/status/reboot", model=Task)
            await self.run_sync(self.proxmox_compute.wait_for_task, task=task)
        else:
            await self.start(vmid=vmid)

    async def stop(self, vmid: int, *, shutdown: bool = False) -> None:
        """Stop a running LXC container."""
        node = self.proxmox_compute.get_node_for_vmid(vmid=vmid)
        if not node:
            await self.log(f"VMID {vmid} not found in Proxmox.")
            return
        if self.proxmox_compute.get_lxc_status(vmid=vmid) == "running":
            status = "shutdown" if shutdown else "stop"
            await self.log(f"Setting VMID {vmid} on node {node} to {status}")
            task = self.proxmox_compute.create(path=f"/nodes/{node}/lxc/{vmid}/status/{status}", model=Task)
            await self.run_sync(self.proxmox_compute.wait_for_task, task=task)
        else:
            await self.log(f"VMID {vmid} on node {node} already stopped.")

    async def terminate(self, vmid: int) -> None:
        """Terminate an LXC container."""
        node = self.proxmox_compute.get_node_for_vmid(vmid=vmid)
        if not node:
            await self.log(f"VMID {vmid} not found in Proxmox.")
            return

        await self.stop(vmid=vmid)

        params = {"destroy-unreferenced-disks": 1, "purge": 1}
        await self.log(message=f"Terminating VMID {vmid} on node {node}")
        task = self.proxmox_compute.delete(path=f"/nodes/{node}/lxc/{vmid}", model=Task, **params)
        await self.run_sync(self.proxmox_compute.wait_for_task, task=task)

    async def update_state(self, name: str, status: ComputeStatus, *, vmid: int = 0) -> None:
        """Update the compute state in Redis based on the LXC status or provided status."""
        if vmid:
            final_status = self.proxmox_compute.get_lxc_status(vmid=vmid)
            await self.redis.hset(
                name=name,
                key="state",
                value=ComputeState.RUNNING.value if final_status == "running" else ComputeState.STOPPED.value,
            )  # pyright: ignore[reportGeneralTypeIssues]
        else:
            await self.redis.hset(name=name, key="state", value=ComputeStatus.get_state(status=status).value)  # pyright: ignore[reportGeneralTypeIssues]
        await self.emit_reflex_events(events=[LXCInstancesTableState.cache_clear("running")])


class VMImageUtils(_Util):
    """Utility class for VM image operations."""

    @cached_property
    def proxmox_compute_templates(self) -> ProxmoxComputeTemplates:
        """Get the Proxmox compute templates client instance."""
        return ProxmoxComputeTemplates()
    
    @cached_property
    def proxmox_compute(self) -> ProxmoxCompute:
        """Get the Proxmox compute client instance."""
        return ProxmoxCompute()

    async def get_volume_id(self, node: str, storage: str, filename: str) -> str:
        stored_images = self.proxmox_compute_templates.list_stored_images(node=node, storage=storage)
        return stored_images.get_image(filename=filename).volid

    async def delete(self, node: str, storage: str, volume_id: str) -> None:
        """Delete a VM image from Proxmox storage."""
        await self.log(message=f"Deleting image {volume_id} from {storage} on {node}")
        task = self.proxmox_compute_templates.delete(
            path=f"/nodes/{node}/storage/{storage}/content/{volume_id}",
            model=Task,
        )
        await self.run_sync(self.proxmox_compute_templates.wait_for_task, task=task)

    async def download(self, params: dict, node: str, storage: str) -> str:
        """Download a VM image to Proxmox storage."""
        await self.log(message=f"Downloading image to {storage} on {node} with params: {params}")
        task = self.proxmox_compute_templates.create(
            path=f"/nodes/{node}/storage/{storage}/download-url",
            model=Task,
            **params,
        )
        await self.run_sync(self.proxmox_compute_templates.wait_for_task, task=task)

    async def file_write(self, vmid: int, file: File) -> None:
        """Push a file to the VM."""
        await self.log(f"Writing source {file.source} contents to {file.destination} on {vmid}")
        params = {"content": file.source.read_text(), "file": str(file.destination)}
        node = self.proxmox_compute_templates.get_node_for_vmid(vmid=vmid)
        await self.run_sync(
            func=self.proxmox_compute_templates.create,
            path=f"/nodes/{node}/qemu/{vmid}/agent/file-write",
            model=None,
            **params,
        )

    async def execute_script(self, vmid: int, script: ScriptStep) -> AgentExecStatus:
        """Execute a script on a virtual machine and return the execution status."""
        node = self.proxmox_compute_templates.get_node_for_vmid(vmid=vmid)
        filename = f"/tmp/{hashlib.md5(script.name.encode()).hexdigest()}.sh"  # noqa: S324
        script_template = Template("#!/bin/bash\nset -euo pipefail\n$content\nrm -f $filename\n")

        await self.log(f"Writing script {script.name} to {vmid} as {filename}")
        await self.run_sync(
            func=self.proxmox_compute_templates.create,
            path=f"/nodes/{node}/qemu/{vmid}/agent/file-write",
            model=None,
            content=script_template.safe_substitute(content=script.script, filename=filename),
            file=filename,
        )

        pid_response = self.proxmox_compute_templates.create(
            path=f"/nodes/{node}/qemu/{vmid}/agent/exec",
            model=AgentExecPid,
            command=["bash", filename],
        )
        status = self.proxmox_compute_templates.get(
            path=f"/nodes/{node}/qemu/{vmid}/agent/exec-status",
            model=AgentExecStatus,
            pid=pid_response.pid,
        )
        while not status.exited:
            await self.log(message=f"Waiting for agent PID {pid_response.pid} to finish...")
            await asyncio.sleep(2)
            status = self.proxmox_compute_templates.get(
                path=f"/nodes/{node}/qemu/{vmid}/agent/exec-status",
                model=AgentExecStatus,
                pid=pid_response.pid,
            )
        await self.log(message=f"Agent PID {pid_response.pid} exited with code: {status.exitcode}")
        return status

    async def generate_image(self, vmid: int, name: str, disk_storage: str, image_storage: str) -> None:
        """Generate a QCOW2 image from a virtual machine disk and upload it to storage."""
        volume_id = self.proxmox_compute.get_vm_root_volume_id(vmid=vmid)
        node = self.proxmox_compute_templates.get_node_for_vmid(vmid=vmid)
        volume = self.proxmox_compute_templates.get(
            path=f"/nodes/{node}/storage/{disk_storage}/content/{volume_id}",
            model=VolumeContentInfo,
        )
        temp_name = hashlib.sha256(volume_id.encode()).hexdigest()
        convert_command = Template("qemu-img convert -p -O qcow2 $path /var/tmp/pveupload-$temp_name")
        conn = self.proxmox_compute_templates.create_connection(node=node)
        await self.log(message=f"Running command {convert_command} on node: {node}")
        await self.run_sync(
            func=conn.run_command,
            command=convert_command.safe_substitute(path=volume.path, temp_name=temp_name),
        )

        params = {
            "content": "import",
            "filename": f"{name}.qcow2",
            "tmpfilename": f"/var/tmp/pveupload-{temp_name}",
        }
        await self.log(message=f"Uploading image to {image_storage}@{node} with params: {params}")
        task = self.proxmox_compute_templates.create(
            path=f"/nodes/{node}/storage/{image_storage}/upload",
            model=Task,
            **params,
        )
        await self.run_sync(self.proxmox_compute_templates.wait_for_task, task=task)


class LXCApplianceUtils(_Util):
    """Utility class for LXC appliance operations."""

    @cached_property
    def proxmox_compute_templates(self) -> ProxmoxComputeTemplates:
        """Get the Proxmox compute templates client instance."""
        return ProxmoxComputeTemplates()

    async def get_volume_id(self, node: str, storage: str, filename: str) -> str:
        stored = self.proxmox_compute_templates.list_stored_appliances(node=node, storage=storage)
        return stored.get_appliance(filename=filename).volid

    async def download(self, node: str, storage: str, template: str) -> None:
        """Download an LXC appliance template to Proxmox storage."""
        await self.log(f"Downloading {template} to {storage}@{node}")
        task = self.proxmox_compute_templates.create(
            path=f"/nodes/{node}/aplinfo",
            model=Task,
            storage=storage,
            template=template,
        )
        await self.run_sync(self.proxmox_compute_templates.wait_for_task, task=task)

    async def delete(self, node: str, storage: str, volume_id: str) -> None:
        """Delete an LXC appliance template from Proxmox storage."""
        await self.log(f"Deleting {volume_id}")
        task = self.proxmox_compute_templates.delete(
            path=f"/nodes/{node}/storage/{storage}/content/{volume_id}",
            model=Task,
        )
        await self.run_sync(self.proxmox_compute_templates.wait_for_task, task=task)

    async def generate_appliance(self, vmid: int, node: str, storage: str, name: str) -> None:
        """Generate an LXC appliance template from a container and upload it to storage."""
        params = {"vmid": vmid, "quiet": 1, "compress": "gzip", "dumpdir": "/var/tmp"}
        await self.log(f"Generating appliance from {vmid}@{node} with params: {params}")
        task = self.proxmox_compute_templates.create(path=f"/nodes/{node}/vzdump", model=Task, **params)
        await self.run_sync(self.proxmox_compute_templates.wait_for_task, task=task)

        temp_name = hashlib.sha256(name.encode()).hexdigest()
        command = f"mv /var/tmp/vzdump-lxc-{vmid}-*.tar.gz /var/tmp/pveupload-{temp_name}"
        conn = self.proxmox_compute_templates.create_connection(node=node)
        await self.log(f"Copying generated appliance via command: {command}")
        await self.run_sync(conn.run_command, command=command)

        params = {
            "content": "vztmpl",
            "filename": f"{name}.tar.gz",
            "tmpfilename": f"/var/tmp/pveupload-{temp_name}",
        }
        await self.log(f"Uploading to {storage}@{node} with params: {params}")
        task = self.proxmox_compute_templates.create(
            path=f"/nodes/{node}/storage/{storage}/upload",
            model=Task,
            **params,
        )
        await self.run_sync(self.proxmox_compute_templates.wait_for_task, task=task)


class DNSUtils(_Util):
    """Utility class for DNS operations."""

    @cached_property
    def dns_vmid(self) -> int:
        """Get the VMID of the DNS server from the cluster manifest."""
        manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        return manifest.spec.backplane.dns_vmid

    async def add_a_record(self, address: IPv4Address, hostname: str, *, record_type: RecordType = "internal") -> None:
        """Add a DNS record for the given hostname and address."""
        conn = self.proxmox.create_connection()
        await self.log(message=f"Adding {record_type} Backplane DNS Record: {hostname}.orbitlab.internal -> {address}")
        await self.run_sync(
            conn.lxc_execute_script,
            vmid=self.dns_vmid,
            content=f"obd-tool add-record {record_type} {address} {hostname}",
        )

    async def delete_a_record(self, address: IPv4Address, *, record_type: RecordType = "internal") -> None:
        """Delete a DNS record for the given address."""
        conn = self.proxmox.create_connection()
        await self.log(message=f"Deleting {record_type} Backplane DNS records for {address}")
        await self.run_sync(
            conn.lxc_execute_script,
            vmid=self.dns_vmid,
            content=f"obd-tool delete-record {record_type} {address}",
        )

    async def add_srv_record(self, service_name: str, port: int, target_name: str, *, protocol: str = "tcp") -> None:
        """Add a DNS SRV record for the given service name, port, and target."""
        conn = self.proxmox.create_connection()
        await self.log(
            message=f"Creating SRV record '_{service_name}._{protocol}' targeting '{target_name}' on port {port}",
        )
        await self.run_sync(
            conn.lxc_execute_script,
            vmid=self.dns_vmid,
            content=f"obd-tool add-srv {service_name} {protocol} {port} {target_name}",
        )

    async def delete_srv_record(self, service_name: str, port: int, target_name: str, *, protocol: str = "tcp") -> None:
        """Delete a DNS SRV record for the given service name, port, and target."""
        conn = self.proxmox.create_connection()
        await self.log(
            message=f"Deleting SRV record '_{service_name}._{protocol}' -> {target_name} for port {port}",
        )
        await self.run_sync(
            conn.lxc_execute_script,
            vmid=self.dns_vmid,
            content=f"obd-tool delete-srv {service_name} {protocol} {port} {target_name}",
        )

    async def add_cname_record(self, name: str, cname: str, *, record_type: RecordType = "internal") -> None:
        """Add a DNS CNAME record for the given name and CNAME target."""
        conn = self.proxmox.create_connection()
        await self.log(message=f"Creating {record_type} CNAME {cname} for record '{name}.orbitlab.internal'")
        await self.run_sync(
            conn.lxc_execute_script,
            vmid=self.dns_vmid,
            content=f"obd-tool add-cname {record_type} {name} {cname}",
        )

    async def delete_cname_record(self, cname: str, *, record_type: RecordType = "internal") -> None:
        """Delete a DNS CNAME record for the given CNAME."""
        conn = self.proxmox.create_connection()
        await self.log(message=f"Deleting {record_type} CNAME record '{cname}.orbitlab.internal'")
        await self.run_sync(
            conn.lxc_execute_script,
            vmid=self.dns_vmid,
            content=f"obd-tool delete-cname {record_type} {cname}",
        )

    async def restart_dns(self) -> None:
        """Restart the Backplane DNS service."""
        await self.log(message="Restarting Backplane DNS")
        conn = self.proxmox.create_connection()
        await self.run_sync(
            conn.lxc_execute_script,
            vmid=self.dns_vmid,
            content="systemctl restart coredns",
        )


class SectorUtils(_Util):
    """Utility class for sector network operations."""

    @cached_property
    def proxmox_networks(self) -> ProxmoxNetworks:
        """Get the Proxmox networks client instance."""
        return ProxmoxNetworks()

    async def create_gateway(self, params: dict) -> None:
        """Create a sector gateway on the specified Proxmox node with the given parameters."""
        task = self.proxmox_networks.create(path=f"/nodes/{self.proxmox_networks.__node__}/lxc", model=Task, **params)
        await self.run_sync(self.proxmox_networks.wait_for_task, task=task)

    async def sector_exists(self, tag: int) -> bool:
        """Check if a sector with the given VLAN tag exists."""
        vnets = self.proxmox_networks.list_vnets()
        return vnets.sector_exists(tag=tag)


class DockFSUtils(VMUtils, DNSUtils):
    """Utility class for DockFS operations."""

    async def create_dockfs_node(self, params: dict, dockfs_name: str) -> None:
        """Create a DockFS node (active or passive) with the given parameters."""
        vmid = params["vmid"]
        node_type = "active" if "scsi1" in params else "passive"
        await self.log(f"Creating {node_type} node {vmid} for {dockfs_name}.")
        await self.create(params=params, disk_size=8)
        await self.start(vmid=vmid)

    async def configure_dockfs_node(self, dockfs_name: str, node: DockFsHost, command: list[str]) -> str:
        """Configure a DockFS node (active or passive) and return an error message if configuration fails."""
        node_type = "active" if "create" in command else "passive"
        await self.log(f"Configuring {dockfs_name} {node_type} node {node.vmid}")
        await self.wait_for_agent(vmid=node.vmid)
        status = await self.agent_exec(vmid=node.vmid, command=command)
        if status.exitcode > 0:
            return f"{node_type.capitalize()} node configuration failed: {status.stderr}"
        return ""

    async def promote(self, active: DockFsHost, passive: DockFsHost) -> str:
        """Promote a passive DockFS node to active and return an error message if promotion fails."""
        await self.stop(vmid=active.vmid)
        node = self.proxmox_compute.get_node_for_vmid(vmid=active.vmid)
        await self.log(message=f"Moving scsi0 from {active.vmid}@{node} to {passive.vmid}")
        params = {"disk": "scsi1", "target-disk": "scsi1", "target-vmid": passive.vmid}
        task = self.proxmox_compute.create(path=f"/nodes/{node}/qemu/{active.vmid}/move_disk", model=Task, **params)
        await self.run_sync(self.proxmox_compute.wait_for_task, task=task)
        status = await self.agent_exec(vmid=passive.vmid, command=["dockfs", "promote"])
        if status.exitcode > 0:
            return f"Promotion of {passive} to active failed: {status.stderr}"
        return ""


class DataCoreUtils(LXCUtils, DNSUtils):
    """Utility class for ETCD operations."""

    def _redact_config(self, config: dict) -> dict:
        return {k: "*****" if "password" in k else v for k, v in config.items()}

    async def create_etcd_discovery_records(self, name: str, address: IPv4Interface) -> None:
        """Create DNS discovery records for an ETCD node."""
        await self.add_a_record(address=address.ip, hostname=name)
        await self.add_a_record(address=address.ip, hostname="etcd")
        await self.add_srv_record(service_name="etcd-server", port=2380, target_name=name)
        await self.add_srv_record(service_name="etcd-client", port=2379, target_name=name)

    async def create_etcd_member(
        self, vmid: int, name: str, address: IPv4Interface, cluster_manifest: ClusterManifest,
    ) -> ETCDMember:
        """Create an ETCD node with the given parameters and return the ETCD member."""
        params = cluster_manifest.generate_etcd_member_create_params(vmid=vmid, name=name, address=address)
        await self.create(params=params)
        cluster_manifest.assign_ip(address=address.ip, description=f"ETCD Member {name}@{vmid}")
        return cluster_manifest.generate_empty_etcd().create_member(vmid=vmid, name=name, address=address)

    async def remove_etcd_member(self, vmid: int, name: str) -> None:
        """Remove an ETCD member using the specified VMID."""
        conn = self.proxmox.create_connection()
        await self.log(f"Using VMID {vmid} to remove ETCD member {name}.")
        await self.run_sync(conn.lxc_execute_script, vmid=vmid, content=f"etcd-mgr remove-member {name}")

    async def delete_etcd_member(
        self, vmid: int, name: str, address: IPv4Interface, cluster_manifest: ClusterManifest,
    ) -> None:
        """Delete an ETCD member and clean up associated DNS records and IP assignments."""
        await self.terminate(vmid=vmid)
        await self.delete_srv_record(service_name="etcd-server", port=2380, target_name=name)
        await self.delete_srv_record(service_name="etcd-client", port=2379, target_name=name)
        await self.delete_a_record(address=address.ip)
        cluster_manifest.release_ip(address=address.ip)

    async def create_datacore_config(self, name: str, config: dict) -> None:
        """Create a DataCore configuration using an ETCD node with the given parameters."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        etcd_member = cluster_manifest.spec.etcd.get_active_member()
        await self.log(
            f"Using VMID {etcd_member.vmid} to create {name} with config {self._redact_config(config=config)}.",
        )
        conn = self.proxmox.create_connection()
        await self.run_sync(
            conn.lxc_execute_script,
            vmid=etcd_member.vmid,
            content=f"etcd-mgr create-datacore {name} '{json.dumps(config)}'",
        )

    async def delete_datacore_config(self, name: str) -> None:
        """Delete a DataCore configuration using an ETCD node."""
        cluster_manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        etcd_member = cluster_manifest.spec.etcd.get_active_member()
        await self.log(f"Using VMID {etcd_member.vmid} to delete DataCore {name}.")
        conn = self.proxmox.create_connection()
        await self.run_sync(conn.lxc_execute_script, vmid=etcd_member.vmid, content=f"etcd-mgr delete-datacore {name}")

    async def create_datacore_sector_record(self, sector: str, address: IPv4Interface, name: str) -> None:
        """Create DNS record for a DataCore sector."""
        await self.log(f"Adding Sector {sector} DNS record: {address} -> {name}.")
        manifest = SectorManifest.load(name=sector)
        conn = self.proxmox.create_connection()
        await self.run_sync(
            conn.lxc_execute_script,
            vmid=manifest.metadata.gateway_vmid,
            content=f"sgwtool add-record {address.ip} {name}",
        )

    async def delete_datacore_sector_record(self, sector: str, virtual_router_id: int) -> None:
        """Delete DNS record for a DataCore sector."""
        manifest = SectorManifest.load(name=sector)
        vip = manifest.spec.get_vip_by_vrid(vrid=virtual_router_id)
        if not vip:
            await self.log(f"No VIP in Sector {sector} for virtual router ID {virtual_router_id}.")
            return

        await self.log(f"Deleting Sector {sector} DNS record for {vip.address}.")
        conn = self.proxmox.create_connection()
        await self.run_sync(
            conn.lxc_execute_script,
            vmid=manifest.metadata.gateway_vmid,
            content=f"sgwtool delete-record {vip.address.ip}",
        )

    async def create_datacore_node(self, params: dict) -> None:
        """Create a DataCore node on the specified Proxmox node with the given parameters."""
        vmid: int = params["vmid"]
        await self.log(f"Creating DataCore node VMID {vmid} with params: {self._redact_params(params=params)}.")
        await self.create(params=params)
        await self.start(vmid=vmid)


class SecretUtils(_Util):
    async def replace_secrets(self, value: str) -> str:
        pattern = re.compile(r"{{secret:(?P<path>[^}]+)}}")
        for secret_name in re.findall(pattern, value):
            secret = SecretManifest.load_from_name(secret_name=secret_name)
            # TODO: finish
            pass


class PKIUtils(_Util):
    """Utility class for PKI operations."""

    @cached_property
    def cert_client(self) -> Certificates:
        """Get the Proxmox client instance."""
        return Certificates()

    async def create_root(self, manifest: RootCertificateManifest) -> None:
        """Create a root certificate authority with the given manifest."""
        await self.run_sync(self.cert_client.create_certificate_authority, manifest=manifest)

    async def create_intermediate(self, manifest: IntermediateCertificateManifest) -> None:
        """Create a root certificate authority with the given manifest."""
        await self.run_sync(self.cert_client.create_intermediate_certificate, manifest=manifest)

    async def create_leaf(self, manifest: LeafCertificateManifest) -> None:
        """Create a leaf certificate with the given manifest."""
        await self.run_sync(self.cert_client.create_leaf_certificate, manifest=manifest)


class InfraUtils(_Util):
    @cached_property
    def proxmox_compute_templates(self) -> ProxmoxComputeTemplates:
        """Get the Proxmox compute templates client instance."""
        return ProxmoxComputeTemplates()

    async def get_storage(self, content_type: StorageContentType, manifest: ClusterManifest) -> str:
        if default_storage := manifest.get_default_storage(content_type=content_type):
            return default_storage
        await self.log(f"Default {content_type} storage not set")
        return next(iter(
            self.proxmox_compute_templates.list_storages_for_node(
                node=manifest.spec.defaults.node, content_type=content_type,
            )
        ))

    async def remove_old_appliance(self, old_appliance: InfraAppliance) -> None:
        manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        storage = old_appliance.volume_id.split(":")[0]
        await self.log(f"Removing older appliance {old_appliance.volume_id} from {storage}")
        
        task = self.proxmox_compute_templates.delete(
            path=f"/nodes/{manifest.spec.defaults.node}/storage/{storage}/content/{old_appliance.volume_id}",
            model=Task,
        )
        await self.run_sync(self.proxmox_compute_templates.wait_for_task, task=task)

    async def download_infrastructure_appliance(
        self, appliance_type: OrbitLabApplianceType, appliance: OrbitLabAppliance,
    ) -> tuple[OrbitLabApplianceType, InfraAppliance]:
        manifest = ClusterManifest.load(name=next(iter(ClusterManifest.get_existing())))
        if appliance.filename.endswith(".qcow2"):
            storage = await self.get_storage(manifest=manifest, content_type=StorageContentType.IMPORT)
            content = "import"
        else:
            storage = await self.get_storage(manifest=manifest, content_type=StorageContentType.VZTMPL)
            content = "vztmpl"

        await self.log(f"Downloading appliance: {appliance.filename}")
        checksum_algorithm, checksum = appliance.digest.split(":")
        params = {
            "content": content,
            "url": appliance.browser_download_url,
            "filename": appliance.filename,
            "checksum": checksum,
            "checksum-algorithm": checksum_algorithm,
        }
        task = self.proxmox_compute_templates.create(
            path=f"/nodes/{manifest.spec.defaults.node}/storage/{storage}/download-url", model=Task, **params,
        )
        await self.run_sync(self.proxmox_compute_templates.wait_for_task, task=task)
        if appliance.filename.endswith(".qcow2"):
            stored = self.proxmox_compute_templates.list_stored_images(node=manifest.spec.defaults.node, storage=storage)
            volume_id = stored.get_image(filename=appliance.filename).volid
        else:
            stored = self.proxmox_compute_templates.list_stored_appliances(node=manifest.spec.defaults.node, storage=storage)
            volume_id = stored.get_appliance(filename=appliance.filename).volid
        
        return (
            appliance_type,
            InfraAppliance(node=manifest.spec.defaults.node, volume_id=volume_id),
        )
