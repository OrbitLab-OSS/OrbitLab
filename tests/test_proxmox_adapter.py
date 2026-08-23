"""Tests for PVE creation semantics that must survive worker concurrency."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx

from orbitlab.proxmox.adapter import ProxmoxAdapter


class FakeProxmox:
    """PVE double that lets tests control VMID collision behavior."""

    def __init__(self, vmids: list[int], collisions: int = 0) -> None:
        self._vmids = iter(vmids)
        self._collisions = collisions
        self.created: list[dict] = []

    async def get_next_vmid(self) -> int:
        return next(self._vmids)

    async def create_instance(self, *, instance_type: str, params: dict, node: str) -> None:
        if self._collisions:
            self._collisions -= 1
            request = httpx.Request("POST", "https://pve.invalid/api2/json/nodes/pve/lxc")
            response = httpx.Response(409, request=request, text="VMID already exists")
            raise httpx.HTTPStatusError("VMID already exists", request=request, response=response)
        self.created.append({"type": instance_type, "params": params, "node": node})


class ExistingGuestProxmox(FakeProxmox):
    """PVE double for recovery after PVE succeeded before a Redis commit."""

    async def list_compute(self) -> SimpleNamespace:
        return SimpleNamespace(root=[SimpleNamespace(vmid=104, node="pve-a", type="lxc")])

    async def get(self, *, path: str, model: object) -> dict[str, str]:
        assert path == "/nodes/pve-a/lxc/104/config"
        assert model is None
        return {"description": "orbitlab-resource:i-existing"}


def test_managed_guest_retries_vmid_collision_before_returning_assignment() -> None:
    proxmox = FakeProxmox([100, 101], collisions=1)
    adapter = ProxmoxAdapter(proxmox=proxmox)  # type: ignore[arg-type]

    guest = asyncio.run(
        adapter.create_managed_guest(
            resource_id="i-test",
            instance_type="lxc",
            node="pve-a",
            parameters=lambda vmid: {"hostname": "test", "vmid": vmid},
        )
    )

    assert guest.vmid == 101
    assert proxmox.created[0]["params"]["description"] == "orbitlab-resource:i-test"
    assert proxmox.created[0]["params"]["tags"] == "orbitlab"


def test_managed_guest_recovers_pve_identity_before_allocating_another_vmid() -> None:
    proxmox = ExistingGuestProxmox([999])
    adapter = ProxmoxAdapter(proxmox=proxmox)  # type: ignore[arg-type]

    guest = asyncio.run(
        adapter.create_managed_guest(
            resource_id="i-existing",
            instance_type="lxc",
            node="pve-a",
            parameters=lambda vmid: {"hostname": "should-not-be-created", "vmid": vmid},
        )
    )

    assert guest.vmid == 104
    assert proxmox.created == []
