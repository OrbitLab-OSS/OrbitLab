"""Web pages package.

This package aggregates all page definitions from various modules.
"""

from .compute import __pages__ as compute_pages
from .conduit import __pages__ as conduit_pages
from .datacore import __pages__ as datacore_pages
from .dockfs import __pages__ as dockfs_pages
from .nodes import __pages__ as node_pages
from .secrets_pki import __pages__ as secret_pki_pages
from .sectors import __pages__ as network_pages
from .logs import __pages__ as logs_pages
from .home import __pages__ as home_pages

pages = (
    *home_pages,
    *compute_pages,
    *node_pages,
    *secret_pki_pages,
    *network_pages,
    *dockfs_pages,
    *datacore_pages,
    *logs_pages,
    *conduit_pages,
)
