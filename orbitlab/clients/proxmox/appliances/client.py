"""Proxmox Appliances Client."""

import hashlib
import time

import httpx

from orbitlab.clients.proxmox.base import Proxmox, Task
from orbitlab.data_types import ApplianceType, CustomApplianceWorkflowStatus, OrbitLabApplianceType
from orbitlab.manifest.appliances import BaseApplianceManifest, CustomApplianceManifest, FileStep, ScriptStep

from .models import ApplianceInfo, Appliances, LatestRelease, StoredAppliances


class ProxmoxAppliances(Proxmox):
    """Client for managing Proxmox appliances."""

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
        task = self.create(path=f"/nodes/{appliance.spec.node.name}/aplinfo", model=Task, **params)
        self.wait_for_task(node=task.node, upid=task.upid)

    def download_latest_orbitlab_appliance(self, storage: str, appliance_type: OrbitLabApplianceType) -> str:
        """Download the latest appliance template from GitHub releases."""
        latest = self.get_latest_release(appliance_type=appliance_type)
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
        self.wait_for_task(node=task.node, upid=task.upid)
        return appliance.name

    def list_stored_appliances(self, node: str, storage: str) -> StoredAppliances:
        """List stored appliance templates in the specified storage on a Proxmox node."""
        params = {"content": "vztmpl"}
        return self.get(f"/nodes/{node}/storage/{storage}/content", model=StoredAppliances, **params)

    def run_workflow(self, appliance: CustomApplianceManifest) -> None:
        """Run the workflow to create a custom appliance on Proxmox."""
        try:
            # Create and Start LXC
            vmid = str(self.get_next_vmid())
            params = appliance.workflow_params(vmid=vmid)
            appliance.set_workflow_status(status=CustomApplianceWorkflowStatus.STARTING)
            appliance.workflow_log(message=f"Creating and starting LXC {vmid}", truncate=True)
            self.create_lxc(node=appliance.spec.node, params=params, start=True)
            time.sleep(10)
            # Run Workflow Steps
            conn = self.create_connection(node=appliance.spec.node)
            appliance.set_workflow_status(status=CustomApplianceWorkflowStatus.RUNNING)
            for step in appliance.spec.steps:
                if isinstance(step, FileStep):
                    appliance.workflow_log(message=f"Executing Files Step: {step.name}")
                    for file in step.files:
                        appliance.workflow_log(message=f"Pushing File: {file.source} to {file.destination}")
                        conn.lxc_push_file(vmid=vmid, source=file.source, destination=file.destination)
                elif isinstance(step, ScriptStep):
                    appliance.workflow_log(message=f"Executing Script Step: {step.name}")
                    conn.lxc_execute_script(vmid=vmid, content=step.script)
            if not appliance.spec.steps:
                appliance.workflow_log(message="No steps to execute")
            # Shutdown LXC
            appliance.workflow_log(message=f"Shutting Down LXC {vmid}")
            task = self.create(path=f"/nodes/{appliance.spec.node}/lxc/{vmid}/status/shutdown", model=Task)
            appliance.set_workflow_status(status=CustomApplianceWorkflowStatus.FINALIZING)
            self.wait_for_task(node=task.node, upid=task.upid)
            # Create Appliance via vzdump
            appliance.workflow_log(message=f"Converting LXC {vmid} to appliance")
            params = {"vmid": vmid, "quiet": 1, "compress": "gzip", "dumpdir": "/var/tmp"}
            task = self.create(path=f"/nodes/{appliance.spec.node}/vzdump", model=Task, **params)
            self.wait_for_task(node=task.node, upid=task.upid)
            temp_name = hashlib.sha256(appliance.name.encode()).hexdigest()
            conn.run_command(command=f"mv /var/tmp/vzdump-lxc-{vmid}-*.tar.gz /var/tmp/pveupload-{temp_name}")
            conn.run_command(command="rm -f /var/tmp/*.log")  # Remove vzdump log file
            params = {
                "content": "vztmpl",
                "filename": f"{appliance.name}.tar.gz",
                "tmpfilename": f"/var/tmp/pveupload-{temp_name}",
            }
            task = self.create(
                path=f"/nodes/{appliance.spec.node}/storage/{appliance.spec.storage}/upload",
                model=Task,
                **params,
            )
            self.wait_for_task(node=task.node, upid=task.upid)
            # Delete LXC
            appliance.workflow_log(message=f"Destroying LXC {vmid}")
            params = {"destroy-unreferenced-disks": 1, "force": 1, "purge": 1}
            task = self.delete(path=f"/nodes/{self.__node__}/lxc/{vmid}", model=Task, **params)
            self.wait_for_task(node=task.node, upid=task.upid)
        except Exception as err:  # noqa: BLE001
            appliance.workflow_log(message=f"{err}")
            appliance.set_workflow_status(status=CustomApplianceWorkflowStatus.FAILED)
        else:
            appliance.set_workflow_status(status=CustomApplianceWorkflowStatus.SUCCEEDED)

    def delete_custom_appliance(self, appliance: CustomApplianceManifest) -> None:
        """Delete a custom appliance from the specified Proxmox storage."""
        task = self.delete(
            path=f"/nodes/{appliance.spec.node}/storage/{appliance.spec.storage}/content/{appliance.volume_id}",
            model=Task,
        )
        self.wait_for_task(node=task.node, upid=task.upid)
