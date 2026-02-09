"""Proxmox Compute Client."""

import functools
import ipaddress
from typing import TYPE_CHECKING

import httpx

from orbitlab.clients.proxmox.base import Proxmox, Task
from orbitlab.data_types import ComputeStatus
from orbitlab.manifest.compute_templates import BaseImageManifest

from .models import Asset, LXCInterfaces, ReleasedImages, VMInterfaces

if TYPE_CHECKING:
    from orbitlab.manifest.compute_instances import LXCManifest, VMManifest


class ProxmoxCompute(Proxmox):
    """Proxmox Compute (VM/LXC) management client."""

    @classmethod
    def get_vendored_images(cls) -> ReleasedImages:
        """Retrieve the latest released images from the VendoredImages GitHub repository."""

        @functools.lru_cache
        def _call() -> dict:
            return {
                "url": "https://api.github.com/repos/OrbitLab-OSS/VendoredImages/releases/277653156",
                "assets_url": "https://api.github.com/repos/OrbitLab-OSS/VendoredImages/releases/277653156/assets",
                "upload_url": "https://uploads.github.com/repos/OrbitLab-OSS/VendoredImages/releases/277653156/assets{?name,label}",
                "html_url": "https://github.com/OrbitLab-OSS/VendoredImages/releases/tag/20260117",
                "id": 277653156,
                "author": {
                    "login": "github-actions[bot]",
                    "id": 41898282,
                    "node_id": "MDM6Qm90NDE4OTgyODI=",
                    "avatar_url": "https://avatars.githubusercontent.com/in/15368?v=4",
                    "gravatar_id": "",
                    "url": "https://api.github.com/users/github-actions%5Bbot%5D",
                    "html_url": "https://github.com/apps/github-actions",
                    "followers_url": "https://api.github.com/users/github-actions%5Bbot%5D/followers",
                    "following_url": "https://api.github.com/users/github-actions%5Bbot%5D/following{/other_user}",
                    "gists_url": "https://api.github.com/users/github-actions%5Bbot%5D/gists{/gist_id}",
                    "starred_url": "https://api.github.com/users/github-actions%5Bbot%5D/starred{/owner}{/repo}",
                    "subscriptions_url": "https://api.github.com/users/github-actions%5Bbot%5D/subscriptions",
                    "organizations_url": "https://api.github.com/users/github-actions%5Bbot%5D/orgs",
                    "repos_url": "https://api.github.com/users/github-actions%5Bbot%5D/repos",
                    "events_url": "https://api.github.com/users/github-actions%5Bbot%5D/events{/privacy}",
                    "received_events_url": "https://api.github.com/users/github-actions%5Bbot%5D/received_events",
                    "type": "Bot",
                    "user_view_type": "public",
                    "site_admin": False,
                },
                "node_id": "RE_kwDOQ6eELc4QjKak",
                "tag_name": "20260117",
                "target_commitish": "main",
                "name": "Vendored Images 20260117",
                "draft": False,
                "immutable": False,
                "prerelease": False,
                "created_at": "2026-01-17T21:13:22Z",
                "updated_at": "2026-01-17T21:17:14Z",
                "published_at": "2026-01-17T21:17:14Z",
                "assets": [
                    {
                        "url": "https://api.github.com/repos/OrbitLab-OSS/VendoredImages/releases/assets/342022233",
                        "id": 342022233,
                        "node_id": "RA_kwDOQ6eELc4UYthZ",
                        "name": "orbitlab-debian-13-amd64-20260117.qcow2",
                        "label": "",
                        "uploader": {
                            "login": "github-actions[bot]",
                            "id": 41898282,
                            "node_id": "MDM6Qm90NDE4OTgyODI=",
                            "avatar_url": "https://avatars.githubusercontent.com/in/15368?v=4",
                            "gravatar_id": "",
                            "url": "https://api.github.com/users/github-actions%5Bbot%5D",
                            "html_url": "https://github.com/apps/github-actions",
                            "followers_url": "https://api.github.com/users/github-actions%5Bbot%5D/followers",
                            "following_url": "https://api.github.com/users/github-actions%5Bbot%5D/following{/other_user}",
                            "gists_url": "https://api.github.com/users/github-actions%5Bbot%5D/gists{/gist_id}",
                            "starred_url": "https://api.github.com/users/github-actions%5Bbot%5D/starred{/owner}{/repo}",
                            "subscriptions_url": "https://api.github.com/users/github-actions%5Bbot%5D/subscriptions",
                            "organizations_url": "https://api.github.com/users/github-actions%5Bbot%5D/orgs",
                            "repos_url": "https://api.github.com/users/github-actions%5Bbot%5D/repos",
                            "events_url": "https://api.github.com/users/github-actions%5Bbot%5D/events{/privacy}",
                            "received_events_url": "https://api.github.com/users/github-actions%5Bbot%5D/received_events",
                            "type": "Bot",
                            "user_view_type": "public",
                            "site_admin": False,
                        },
                        "content_type": "application/octet-stream",
                        "state": "uploaded",
                        "size": 704970752,
                        "digest": "sha256:9ef0caf2f11ae9c63ad0bd6b5cec13fc6d4525bfca69aab9691252afa5760fa6",
                        "download_count": 2,
                        "created_at": "2026-01-17T21:16:59Z",
                        "updated_at": "2026-01-17T21:17:13Z",
                        "browser_download_url": "https://github.com/OrbitLab-OSS/VendoredImages/releases/download/20260117/orbitlab-debian-13-amd64-20260117.qcow2",
                    },
                    {
                        "url": "https://api.github.com/repos/OrbitLab-OSS/VendoredImages/releases/assets/342022232",
                        "id": 342022232,
                        "node_id": "RA_kwDOQ6eELc4UYthY",
                        "name": "orbitlab-debian-13-amd64-20260117.qcow2.sha256",
                        "label": "",
                        "uploader": {
                            "login": "github-actions[bot]",
                            "id": 41898282,
                            "node_id": "MDM6Qm90NDE4OTgyODI=",
                            "avatar_url": "https://avatars.githubusercontent.com/in/15368?v=4",
                            "gravatar_id": "",
                            "url": "https://api.github.com/users/github-actions%5Bbot%5D",
                            "html_url": "https://github.com/apps/github-actions",
                            "followers_url": "https://api.github.com/users/github-actions%5Bbot%5D/followers",
                            "following_url": "https://api.github.com/users/github-actions%5Bbot%5D/following{/other_user}",
                            "gists_url": "https://api.github.com/users/github-actions%5Bbot%5D/gists{/gist_id}",
                            "starred_url": "https://api.github.com/users/github-actions%5Bbot%5D/starred{/owner}{/repo}",
                            "subscriptions_url": "https://api.github.com/users/github-actions%5Bbot%5D/subscriptions",
                            "organizations_url": "https://api.github.com/users/github-actions%5Bbot%5D/orgs",
                            "repos_url": "https://api.github.com/users/github-actions%5Bbot%5D/repos",
                            "events_url": "https://api.github.com/users/github-actions%5Bbot%5D/events{/privacy}",
                            "received_events_url": "https://api.github.com/users/github-actions%5Bbot%5D/received_events",
                            "type": "Bot",
                            "user_view_type": "public",
                            "site_admin": False,
                        },
                        "content_type": "application/octet-stream",
                        "state": "uploaded",
                        "size": 106,
                        "digest": "sha256:8beb3d3e92a1e274c1bde68522fde9a501820c57923f4b765a52a5488a072aeb",
                        "download_count": 1,
                        "created_at": "2026-01-17T21:16:59Z",
                        "updated_at": "2026-01-17T21:17:00Z",
                        "browser_download_url": "https://github.com/OrbitLab-OSS/VendoredImages/releases/download/20260117/orbitlab-debian-13-amd64-20260117.qcow2.sha256",
                    },
                ],
                "tarball_url": "https://api.github.com/repos/OrbitLab-OSS/VendoredImages/tarball/20260117",
                "zipball_url": "https://api.github.com/repos/OrbitLab-OSS/VendoredImages/zipball/20260117",
                "body": None,
            }
            with httpx.Client() as client:
                response = client.get("https://api.github.com/repos/OrbitLab-OSS/VendoredImages/releases/latest")
            response.raise_for_status()
            print(response.json())
            return response.json()

        return ReleasedImages.model_validate(_call())

    def download_vendored_image(self, storage: str, asset: Asset) -> None:
        """Download a vendored image to the specified storage."""
        checksum_algorithm, checksum = asset.digest.split(":")
        params = {
            "content": "import",
            "url": asset.browser_download_url,
            "filename": asset.name,
            "checksum": checksum,
            "checksum-algorithm": checksum_algorithm,
        }
        task = self.create(path=f"/nodes/{self.__node__}/storage/{storage}/download-url", model=Task, **params)
        self.wait_for_task(task=task)

    def update_vendored_image(self, image: BaseImageManifest, asset: Asset) -> None:
        """Update a vendored image by deleting the existing image and downloading the new asset."""
        task = self.delete(
            path=f"/nodes/{image.spec.node}/storage/{image.spec.storage}/content/{image.volume_id}",
            model=Task,
        )
        self.wait_for_task(task=task)
        self.download_vendored_image(storage=image.spec.storage, asset=asset)
        image.update(asset=asset)

    def launch_lxc(self, lxc: "LXCManifest") -> int:
        """Create an LXC compute resource."""
        vmid = self.get_next_vmid()
        params = lxc.create_lxc_params(vmid=vmid)
        self.create_lxc(node=lxc.metadata.node, params=params, start=True)
        lxc.set_status(status=ComputeStatus.START, completed=True)
        return vmid

    def set_lxc_status(self, lxc: "LXCManifest", status: ComputeStatus) -> None:
        """Set the status of an LXC container."""
        if not lxc.metadata.vmid:
            return
        node = self.get_node_for_vmid(vmid=lxc.metadata.vmid)
        if status == ComputeStatus.TERMINATE:
            # We can terminate running LXCs without stopping them.
            params = {"destroy-unreferenced-disks": 1, "force": 1, "purge": 1}
            task = self.delete(path=f"/nodes/{node}/lxc/{lxc.metadata.vmid}", model=Task, **params)
            self.wait_for_task(task=task)
            lxc.delete()
            return
        task = self.create(path=f"/nodes/{node}/lxc/{lxc.metadata.vmid}/status/{status}", model=Task)
        self.wait_for_task(task=task)
        lxc.set_status(status=status, completed=True)
        return

    def set_vm_status(self, vm: "VMManifest", status: ComputeStatus) -> None:
        """Set the status of a VM."""
        if vm.metadata.vmid:
            node = self.get_node_for_vmid(vmid=vm.metadata.vmid)
            if status == ComputeStatus.TERMINATE:
                # Stop first or Proxmox gets unhappy.
                task = self.create(path=f"/nodes/{node}/qemu/{vm.metadata.vmid}/status/stop", model=Task)
                self.wait_for_task(task=task)
                # Now delete
                params = {"destroy-unreferenced-disks": 1, "purge": 1}
                task = self.delete(path=f"/nodes/{node}/qemu/{vm.metadata.vmid}", model=Task, **params)
                self.wait_for_task(task=task)
                vm.delete()
                return
            task = self.create(path=f"/nodes/{node}/qemu/{vm.metadata.vmid}/status/{status}", model=Task)
            self.wait_for_task(task=task)
            vm.set_status(status=status, completed=True)
        return

    def launch_vm(self, vm_manifest: "VMManifest") -> None:
        """Create and launch a VM compute resource."""
        vmid = self.get_next_vmid()
        params = vm_manifest.create_vm_params(vmid=vmid)
        self.create_vm(node=self.__node__, params=params, disk_size=vm_manifest.spec.disk_size, start=True)
        vm_manifest.set_status(status=ComputeStatus.START, completed=True)

    def get_lxc_private_ipv4(self, node: str, vmid: int) -> ipaddress.IPv4Interface | None:
        """Retrieve the private IPv4 address of an LXC container."""
        interfaces = self.get(f"/nodes/{node}/lxc/{vmid}/interfaces", model=LXCInterfaces)
        return interfaces.get_default_ipv4()

    def get_vm_private_ipv4(self, node: str, vmid: int) -> ipaddress.IPv4Interface | None:
        """Retrieve the private IPv4 address of an LXC container."""
        try:
            interfaces = self.get(f"/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces", model=VMInterfaces)
        except httpx.HTTPStatusError:
            return None
        return interfaces.get_default_ipv4()

    def _create_pool(self) -> None:
        params = {"poolid": "avp-hf83nd9845h", "comment": "My Pool"}
        self.create("/pools", model=None, **params)

    def _add_vm_to_pool(self) -> None:
        vmid = self.get_next_vmid()
        params = {
            "vmid": vmid,
            "pool": "avp-hf83nd9845h",
            "name": "test",
            "cores": 2,
            "sockets": 1,
            "memory": 2 * 1024,
            "cpu": "x86-64-v2-AES",
            "numa": 0,
            "agent": "enabled=1",
            "serial0": "socket",
            "scsi0": "local:0,import-from=local:import/vmi-fy3tg1vhb9hc.qcow2",
            "ide0": "local:cloudinit",
            "citype": "nocloud",
            "ciuser": "root",
            "cipassword": "asdfasdf",
            "net0": "virtio,bridge=olvn1000",
            "ipconfig0": "gw=192.168.0.1,ip=192.168.0.25/21",
            "searchdomain": "olvn1000.orbitlab.internal",
            "nameserver": "192.168.0.2",
            "scsihw": "virtio-scsi-single",
            "ostype": "l26",
            "onboot": "1",
            "boot": "order=scsi0",
        }
        self.create_vm(node=self.__node__, params=params, disk_size=10, start=True)
