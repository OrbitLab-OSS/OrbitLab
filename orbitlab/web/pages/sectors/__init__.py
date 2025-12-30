"""OrbitLab Networks."""

from .appliances import sectors_appliances
from .dashboard import sectors_dashboard

__pages__ = (
    sectors_dashboard,
    sectors_appliances,
)
