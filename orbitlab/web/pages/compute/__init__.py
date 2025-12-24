"""OrbitLab Compute Management."""

from .dashboard import compute_page
from .lxc import __pages__ as lxc_pages

__pages__ = (
    compute_page,
    *lxc_pages,
)
