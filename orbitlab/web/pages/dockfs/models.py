"""DockFS Models."""

from pydantic import BaseModel


class CreateDockFSform(BaseModel):
    """Form model for creating a DockFS instance."""

    name: str
    storage: str
    capacity_gb: int
    cores: int
    sockets: int
    memory: int
