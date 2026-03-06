"""OrbitLab Compute Management."""

from .autoscaling import __pages__ as autoscaling_pages
from .dashboard import compute_dashboard
from .lxc import __pages__ as lxc_pages
from .vm import __pages__ as vm_pages

__pages__ = (
    compute_dashboard,
    *lxc_pages,
    *vm_pages,
    *autoscaling_pages,
)
