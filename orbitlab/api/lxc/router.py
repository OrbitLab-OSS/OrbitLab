from fastapi import APIRouter

from orbitlab.data_types import ManifestKind
from orbitlab.manifest.client import ManifestClient
from orbitlab.manifest.schemas.lxcs import LXCManifest

router = APIRouter(prefix="/api/v1/lxc", tags=["LXC"])


@router.post("/", status_code=201)
async def create_lxc(manifest: LXCManifest) -> None:
    pass
