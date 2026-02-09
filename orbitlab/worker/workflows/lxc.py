from orbitlab.clients.proxmox.compute.client import ProxmoxCompute
from orbitlab.manifest.compute_instances.lxc import LXCManifest
from .base import Workflow, WorkflowPayload


class LXCCreateV1Payload(WorkflowPayload):
    manifest: str


class LXCCreateV1(Workflow):
    TYPE = "lxc.create"
    SCHEMA = "v1"
    PAYLOAD: type[LXCCreateV1Payload] = LXCCreateV1Payload

    async def pending(self, payload: LXCCreateV1Payload) -> LXCCreateV1Payload:
        if payload.manifest in LXCManifest.get_existing():
            return await self.progress(payload=payload)
        return await self.failed(error=f"LXC Manifest {payload.manifest} does not exist", payload=payload)
    
    async def validate(self, payload: LXCCreateV1Payload) -> LXCCreateV1Payload:
        manifest = LXCManifest.load(name=payload.manifest)
        params = manifest.create_lxc_params(vmid=0)
        if params:
            return await self.progress(payload=payload)
        return await self.failed(
            error=f"Unable to validate LXC creation parameters for {payload.manifest}",
            payload=payload,
        )

    async def provision(self, payload: LXCCreateV1Payload) -> LXCCreateV1Payload:
        manifest = LXCManifest.load(name=payload.manifest)
        vmid = ProxmoxCompute().launch_lxc(lxc=manifest)
        await self.redis.hset(name=f"ol:lxc:{manifest.name}", key="vmid", value=str(vmid)) # pyright: ignore[reportGeneralTypeIssues]
        return await self.progress(payload=payload)

    async def configure(self, payload: LXCCreateV1Payload) -> LXCCreateV1Payload:
        manifest = LXCManifest.load(name=payload.manifest)
        vmid: str | None = await self.redis.hget(name=f"ol:lxc:{manifest.name}", key="vmid") # type: ignore
        if not vmid:
            return await self.failed(error=f"Unable to get VMID for {manifest.name}", payload=payload)
        ip_address = ProxmoxCompute().get_lxc_private_ipv4(node=manifest.metadata.node, vmid=int(vmid))
        if not ip_address:
            return await self.failed(error=f"Unable to get default IPv4 address for VMID {vmid}", payload=payload)
        await self.redis.hset(name=f"ol:lxc:{manifest.name}", key="ipv4", value=ip_address.with_prefixlen) # pyright: ignore[reportGeneralTypeIssues]
        return await self.progress(payload=payload)

    async def on_failure(self, payload: LXCCreateV1Payload) -> LXCCreateV1Payload:
        if not payload.manifest in LXCManifest.get_existing():
            return payload
        manifest = LXCManifest.load(name=payload.manifest)
        await self.redis.hdel(f"ol:lxc:{manifest.name}", "vmid") # pyright: ignore[reportGeneralTypeIssues]
        await self.redis.hdel(f"ol:lxc:{manifest.name}", "ipv4") # pyright: ignore[reportGeneralTypeIssues]
        manifest.delete()
        return payload
