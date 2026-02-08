"""Proxmox Appliances Client."""

import hashlib
import time
from string import Template

import httpx

from orbitlab.clients.proxmox.base import Proxmox, Task
from orbitlab.clients.proxmox.base.client import RemoteExecution
from orbitlab.clients.proxmox.exceptions import AgentExecError, PctExecError
from orbitlab.data_types import ApplianceType, OrbitLabApplianceType, WorkflowStatus
from orbitlab.manifest.compute_templates import (
    BaseApplianceManifest,
    CustomApplianceManifest,
    CustomImageManifest,
    FileStep,
    ScriptStep,
)

from .models import (
    AgentExecPid,
    AgentExecStatus,
    ApplianceInfo,
    Appliances,
    LatestRelease,
    StoredAppliances,
    VolumeContentInfo,
)


class ProxmoxComputeTemplates(Proxmox):
    """Client for managing Proxmox compute templates (LXC appliances and VM images)."""

    def get_latest_release(self, appliance_type: OrbitLabApplianceType) -> LatestRelease:
        """Get the latest release from a given repository."""
        with httpx.Client() as client:
            response = client.get(f"https://api.github.com/repos/OrbitLab-OSS/{appliance_type}/releases/latest")
            response.raise_for_status()
            return LatestRelease.model_validate(response.json())

    def list_appliances(self, appliance_type: ApplianceType | None = None) -> list[ApplianceInfo]:
        """List available LXC appliances on the specified Proxmox node."""
        appliances = self.get(f"/nodes/{self.__node__}/aplinfo", model=Appliances)
        match appliance_type:
            case ApplianceType.SYSTEM:
                return appliances.system_appliances()
            case ApplianceType.TURNKEY:
                return appliances.turnkey_appliances()
            case _:
                return appliances.root

    def download_appliance(self, appliance: "BaseApplianceManifest") -> None:
        """Download an LXC appliance to the specified storage on a Proxmox node."""
        params = {"storage": appliance.spec.storage, "template": appliance.spec.template}
        task = self.create(path=f"/nodes/{appliance.spec.node}/aplinfo", model=Task, **params)
        self.wait_for_task(task=task)

    def download_latest_orbitlab_appliance(self, storage: str, appliance_type: OrbitLabApplianceType) -> str:
        """Download the latest appliance template from GitHub releases."""
        latest = self.get_latest_release(appliance_type=appliance_type)
        if not latest:
            return ""
        appliance = latest.get_appliance_asset()
        checksum_algorithm, checksum = appliance.digest.split(":")
        params = {
            "content": "vztmpl",
            "url": appliance.browser_download_url,
            "filename": appliance.name,
            "checksum": checksum,
            "checksum-algorithm": checksum_algorithm,
        }
        task = self.create(path=f"/nodes/{self.__node__}/storage/{storage}/download-url", model=Task, **params)
        self.wait_for_task(task=task)
        return appliance.name

    def list_stored_appliances(self, node: str, storage: str) -> StoredAppliances:
        """List stored appliance templates in the specified storage on a Proxmox node."""
        params = {"content": "vztmpl"}
        return self.get(f"/nodes/{node}/storage/{storage}/content", model=StoredAppliances, **params)

    def _initialize_compute(self, vmid: int, manifest: CustomApplianceManifest | CustomImageManifest) -> bool:
        params = manifest.workflow_params(vmid=vmid)
        manifest.set_workflow_status(status=WorkflowStatus.STARTING)
        manifest.workflow_log(message=f"Creating and starting VMID {vmid}", truncate=True)
        if isinstance(manifest, CustomApplianceManifest):
            self.create_lxc(node=manifest.spec.node, params=params, start=True)
        else:
            self.create_vm(node=manifest.spec.node, params=params, disk_size=manifest.spec.disk_size, start=True)
        time.sleep(10)
        return True

    def _run_lxc_workflow_steps(self, vmid: int, manifest: CustomApplianceManifest) -> RemoteExecution:
        conn = self.create_connection(node=manifest.spec.node)
        manifest.set_workflow_status(status=WorkflowStatus.RUNNING)
        for step in manifest.spec.steps:
            if isinstance(step, FileStep):
                manifest.workflow_log(message=f"Executing Files Step: {step.name}")
                for file in step.files:
                    manifest.workflow_log(message=f"Pushing File: {file.source} to {file.destination}")
                    conn.lxc_push_file(vmid=vmid, source=file.source, destination=file.destination)
            elif isinstance(step, ScriptStep):
                manifest.workflow_log(message=f"Executing Script Step: {step.name}")
                logs = conn.lxc_execute_script(vmid=vmid, content=step.script)
                manifest.metadata.logs.extend(logs)

        if not manifest.spec.steps:
            manifest.workflow_log(message="No steps to execute")

        manifest.workflow_log(message=f"Shutting Down VMID {vmid}")
        task = self.create(path=f"/nodes/{manifest.spec.node}/lxc/{vmid}/status/shutdown", model=Task)
        manifest.set_workflow_status(status=WorkflowStatus.FINALIZING)
        self.wait_for_task(task=task)
        return conn

    def _wait_for_agent_exec(self, node: str, vmid: int, pid: AgentExecPid) -> AgentExecStatus:
        params = {"pid": pid.pid}
        status = self.get(f"/nodes/{node}/qemu/{vmid}/agent/exec-status", model=AgentExecStatus, **params)
        while not status.exited:
            time.sleep(2)
            status = self.get(f"/nodes/{node}/qemu/{vmid}/agent/exec-status", model=AgentExecStatus, **params)
        return status

    def _wait_for_agent(self, node: str, vmid: int) -> None:
        while True:
            try:
                self.create(f"/nodes/{node}/qemu/{vmid}/agent/ping", model=None)
            except httpx.HTTPStatusError:
                time.sleep(2)
            else:
                break

    def _run_vm_workflow_steps(self, vmid: int, manifest: CustomImageManifest) -> None:
        manifest.set_workflow_status(status=WorkflowStatus.RUNNING)
        for step in manifest.spec.steps:
            if isinstance(step, FileStep):
                manifest.workflow_log(message=f"Executing Files Step: {step.name}")
                for file in step.files:
                    manifest.workflow_log(message=f"Pushing File: {file.source} to {file.destination}")
                    params = {"content": file.source.read_text(), "file": str(file.destination)}
                    self.create(f"/nodes/{manifest.spec.node}/qemu/{vmid}/agent/file-write", model=None, **params)
            elif isinstance(step, ScriptStep):
                manifest.workflow_log(message=f"Executing Script Step: {step.name}")
                filename = f"/tmp/{hashlib.md5(step.name.encode()).hexdigest()}.sh"  # noqa: S324
                script = Template("#!/bin/bash\nset -euo pipefail\n$content\nrm -f $filename\n")
                script_params = {
                    "content": script.safe_substitute(content=step.script, filename=filename),
                    "file": filename,
                }
                command_params = {"command": f"bash {filename}"}
                self.create(f"/nodes/{manifest.spec.node}/qemu/{vmid}/agent/file-write", model=None, **script_params)
                command_params = {"command": ["bash", filename]}
                pid = self.create(
                    path=f"/nodes/{manifest.spec.node}/qemu/{vmid}/agent/exec",
                    model=AgentExecPid,
                    **command_params,
                )
                status: AgentExecStatus = self._wait_for_agent_exec(node=manifest.spec.node, vmid=vmid, pid=pid)
                if status.exitcode and status.exitcode > 0:
                    raise AgentExecError(
                        exit_code=status.exitcode,
                        msg=f"Error running {step.name}",
                        logs=status.logs,
                    )
                manifest.metadata.logs.extend(status.logs)

        if not manifest.spec.steps:
            manifest.workflow_log(message="No steps to execute")

        manifest.workflow_log(message=f"Shutting Down VMID {vmid}")
        task = self.create(path=f"/nodes/{manifest.spec.node}/qemu/{vmid}/status/shutdown", model=Task)
        manifest.set_workflow_status(status=WorkflowStatus.FINALIZING)
        self.wait_for_task(task=task)

    def _create_appliance_from_lxc(self, vmid: int, conn: RemoteExecution, manifest: CustomApplianceManifest) -> None:
        manifest.workflow_log(message=f"Converting LXC {vmid} to appliance")
        params = {"vmid": vmid, "quiet": 1, "compress": "gzip", "dumpdir": "/var/tmp"}
        task = self.create(path=f"/nodes/{manifest.spec.node}/vzdump", model=Task, **params)
        self.wait_for_task(task=task)
        temp_name = hashlib.sha256(manifest.name.encode()).hexdigest()
        conn.run_command(command=f"mv /var/tmp/vzdump-lxc-{vmid}-*.tar.gz /var/tmp/pveupload-{temp_name}")
        conn.run_command(command="rm -f /var/tmp/*.log")  # Remove vzdump log file
        params = {
            "content": "vztmpl",
            "filename": f"{manifest.name}.tar.gz",
            "tmpfilename": f"/var/tmp/pveupload-{temp_name}",
        }
        task = self.create(
            path=f"/nodes/{manifest.spec.node}/storage/{manifest.spec.storage}/upload",
            model=Task,
            **params,
        )
        self.wait_for_task(task=task)

    def _create_image_from_vm(self, vmid: int, manifest: CustomImageManifest) -> None:
        manifest.workflow_log(message=f"Generating image from VMID {vmid}")
        disk_id = f"{manifest.spec.disk_storage}:vm-{vmid}-disk-0"
        volume = self.get(
            f"/nodes/{manifest.spec.node}/storage/{manifest.spec.disk_storage}/content/{disk_id}",
            model=VolumeContentInfo,
        )
        conn = self.create_connection(node=manifest.spec.node)
        temp_name = hashlib.sha256(manifest.name.encode()).hexdigest()
        conn.run_command(command=f"qemu-img convert -p -O qcow2 {volume.path} /var/tmp/pveupload-{temp_name}")
        params = {
            "content": "import",
            "filename": f"{manifest.name}.qcow2",
            "tmpfilename": f"/var/tmp/pveupload-{temp_name}",
        }
        task = self.create(
            path=f"/nodes/{manifest.spec.node}/storage/{manifest.spec.image_storage}/upload",
            model=Task,
            **params,
        )
        self.wait_for_task(task=task)

    def _terminate_compute(
        self,
        vmid: int,
        manifest: CustomApplianceManifest | CustomImageManifest,
        *,
        running: bool,
    ) -> None:
        compute_type = "lxc" if isinstance(manifest, CustomApplianceManifest) else "qemu"
        if running:
            task = self.create(path=f"/nodes/{manifest.spec.node}/{compute_type}/{vmid}/status/stop", model=Task)
            self.wait_for_task(task=task)
        # Delete LXC
        manifest.workflow_log(message=f"Destroying VMID {vmid}")
        params = {"destroy-unreferenced-disks": 1, "purge": 1}
        if compute_type == "lxc":
            params["force"] = 1
        task = self.delete(path=f"/nodes/{self.__node__}/{compute_type}/{vmid}", model=Task, **params)
        self.wait_for_task(task=task)

    def run_workflow(self, manifest: CustomApplianceManifest | CustomImageManifest) -> WorkflowStatus:
        """Run the workflow to create a custom compute template on Proxmox."""
        running = False
        created = False
        vmid = self.get_next_vmid()
        try:
            # Launch Compute
            created = self._initialize_compute(vmid=vmid, manifest=manifest)
            running = True
            # Run Workflow Steps
            if isinstance(manifest, CustomApplianceManifest):
                conn = self._run_lxc_workflow_steps(vmid=vmid, manifest=manifest)
                self._create_appliance_from_lxc(vmid=vmid, conn=conn, manifest=manifest)
            else:
                self._wait_for_agent(node=manifest.spec.node, vmid=vmid)
                self._run_vm_workflow_steps(vmid=vmid, manifest=manifest)
                self._create_image_from_vm(vmid=vmid, manifest=manifest)
            running = False
        except (PctExecError, AgentExecError) as err:
            manifest.workflow_log(message=f"{err}")
            manifest.metadata.logs.extend(err.logs)
            manifest.set_workflow_status(status=WorkflowStatus.FAILED)
        except httpx.HTTPStatusError as err:
            manifest.workflow_log(message=f"{err}")
            manifest.set_workflow_status(status=WorkflowStatus.FAILED)
        else:
            manifest.set_workflow_status(status=WorkflowStatus.SUCCEEDED)
        finally:
            if created:
                self._terminate_compute(vmid=vmid, manifest=manifest, running=running)

        return manifest.metadata.status

    def delete_appliance(self, appliance: CustomApplianceManifest | BaseApplianceManifest) -> None:
        """Delete a custom appliance from the specified Proxmox storage."""
        task = self.delete(
            path=f"/nodes/{appliance.spec.node}/storage/{appliance.spec.storage}/content/{appliance.ostemplate}",
            model=Task,
        )
        self.wait_for_task(task=task)
