"""OrbitLab VM Management."""

from .images import images_page
from .instances import vm_instances

__pages__ = (
    images_page,
    vm_instances,
)
