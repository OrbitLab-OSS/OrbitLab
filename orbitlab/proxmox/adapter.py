"""The single application-facing boundary for Proxmox behavior."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import asyncio
import inspect
from typing import Any

import httpx

from orbitlab.data_types import InstanceType
from orbitlab.proxmox.client import Proxmox


class VMIDConflictError(RuntimeError):
    """Raised when Proxmox reports that a VMID was claimed by another creator."""


@dataclass(frozen=True, slots=True)
class ManagedGuest:
    """The durable result of a successful Proxmox guest creation."""

    resource_id: str
    vmid: int
    node: str
    instance_type: InstanceType


class ProxmoxAdapter:
    """Encapsulates PVE requests, VMID retry, and managed-object identity."""

    VMID_ATTEMPTS = 5
    _sdn_lock = asyncio.Lock()

    def __init__(self, proxmox: Proxmox | None = None) -> None:
        self._proxmox = proxmox or Proxmox()

    @staticmethod
    def resource_identity(resource_id: str) -> str:
        """Return the identity marker written into PVE guest metadata."""
        return f"orbitlab-resource:{resource_id}"

    @staticmethod
    def _is_vmid_conflict(error: Exception) -> bool:
        """Classify PVE's VMID-already-used responses without hiding other failures."""
        if not isinstance(error, httpx.HTTPStatusError):
            return False
        response_text = error.response.text.lower()
        return error.response.status_code in {400, 409, 500} and "vmid" in response_text and any(
            phrase in response_text for phrase in ("already", "exist", "used")
        )

    async def create_managed_guest(
        self,
        *,
        resource_id: str,
        instance_type: InstanceType,
        node: str,
        parameters: Callable[[int], dict[str, Any] | Awaitable[dict[str, Any]]],
    ) -> ManagedGuest:
        """Allocate and immediately create a PVE guest, retrying VMID races.

        PVE must complete creation before a VMID can be committed to Redis. The
        resource identity is stored in PVE metadata, enabling reconciliation if
        a process stops between PVE success and the Redis commit.
        """
        identity = self.resource_identity(resource_id)
        if existing := await self._find_managed_guest(identity):
            return existing
        for attempt in range(1, self.VMID_ATTEMPTS + 1):
            vmid = await self._proxmox.get_next_vmid()
            candidate = parameters(vmid)
            if inspect.isawaitable(candidate):
                candidate = await candidate
            params = dict(candidate)
            params["vmid"] = vmid
            params.setdefault("description", identity)
            params.setdefault("tags", "orbitlab")
            try:
                await self._proxmox.create_instance(instance_type=instance_type, params=params, node=node)
            except Exception as error:  # noqa: BLE001
                if self._is_vmid_conflict(error) and attempt < self.VMID_ATTEMPTS:
                    continue
                if self._is_vmid_conflict(error):
                    raise VMIDConflictError(f"Unable to create {resource_id}: VMID conflicts persisted") from error
                raise
            return ManagedGuest(resource_id=resource_id, vmid=vmid, node=node, instance_type=instance_type)
        raise AssertionError("VMID allocation loop exited unexpectedly")

    async def _find_managed_guest(self, identity: str) -> ManagedGuest | None:
        """Recover a guest created before its Redis commit was able to run.

        The description marker is the durable source of truth across a worker
        restart.  It prevents an initialization or resource-create retry from
        duplicating a guest after PVE accepted the create task but before the
        worker recorded the VMID in Redis.
        """
        if not hasattr(self._proxmox, "list_compute"):
            return None
        for resource in (await self._proxmox.list_compute()).root:
            config = await self._proxmox.get(
                path=f"/nodes/{resource.node}/{resource.type}/{resource.vmid}/config",
                model=None,
            )
            if config.get("description", "") != identity:
                continue
            return ManagedGuest(
                resource_id=identity.removeprefix("orbitlab-resource:"),
                vmid=resource.vmid,
                node=resource.node,
                instance_type=resource.type,
            )
        return None

    async def apply_sdn(self, mutation: Callable[[], Awaitable[None]]) -> None:
        """Serialize cluster-global SDN mutations in this durable worker process."""
        async with self.__class__._sdn_lock:
            await mutation()

    async def close(self) -> None:
        """Release the PVE async session when the process stops."""
        session = self._proxmox.__dict__.get("__session__")
        if session is not None:
            await session.aclose()
