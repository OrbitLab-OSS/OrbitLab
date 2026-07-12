"""OrbitLab Compute Management."""

from .autoscaling import __pages__ as autoscaling_pages
from .page import compute_instances
from .appliances.page import appliances_page
from .images.pages import images_page

__pages__ = (
    compute_instances,
    appliances_page,
    images_page,
    *autoscaling_pages
)
