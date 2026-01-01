"""OrbitLab LXC Management."""

from .appliances import appliances_page
from .running import running_lxcs

__pages__ = (
    appliances_page,
    running_lxcs,
)
