"""Web pages package.

This package aggregates all page definitions from various modules.
"""

from .compute import __pages__ as compute_pages
from .nodes import __pages__ as node_pages
from .secrets_pki import __pages__ as secret_pki_pages
from .sectors import __pages__ as network_pages

pages = (
    *compute_pages,
    *node_pages,
    *secret_pki_pages,
    *network_pages,
)
