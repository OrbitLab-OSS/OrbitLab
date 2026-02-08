"""OrbitLab Networks Dashboard Models."""

from pydantic import BaseModel


class CreateSectorForm(BaseModel):
    """Form model for creating a new sector."""

    tag: int
    name: str
    cidr_block: str

    @property
    def sector_id(self) -> str:
        """Generate the sector ID based on the network tag."""
        return f"olvn{self.tag}"
