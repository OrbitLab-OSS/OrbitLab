"""DockFS Models."""

from pydantic import BaseModel


class CreateDataCoreForm(BaseModel):
    """Form model for creating a DataCore cluster."""

    name: str
    replicas: int
    storage: str
    capacity_gb: int
    cores: int
    memory_gb: int
    sector: str
    application_user: str
    application_database: str
    application_password: str
