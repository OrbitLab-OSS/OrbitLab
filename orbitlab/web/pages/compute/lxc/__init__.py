"""OrbitLab LXC Management."""

from .appliances import appliances_page
from .instances import lxc_instances

__pages__ = (
    appliances_page,
    lxc_instances,
)
