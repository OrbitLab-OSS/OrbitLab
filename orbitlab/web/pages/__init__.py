"""Web pages package.

This package aggregates all page definitions from various modules.
"""

from .compute import pages as compute_pages
from .nodes import pages as node_pages
from .secrets_pki import pages as secret_pki_pages

pages = (
    *compute_pages,
    *node_pages,
    *secret_pki_pages,
)
