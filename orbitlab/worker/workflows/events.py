from pydantic import BaseModel

from orbitlab.data_types import EventStatus


class OrbitLabEvent(BaseModel):
    name: str
    version: str
    job_id: str
    status: EventStatus

    @property
    def redis_key(self) -> str:
        return f"ol:{self.name}:{self.version}:{self.job_id}"
