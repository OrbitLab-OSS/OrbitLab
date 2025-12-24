"""OrbitLab Secrets & PKI."""

from .dashboard import secrets_pki_dashboard
from .manage_secrets import __pages__ as secrets_pages
from .pki import __pages__ as pki_pages

__pages__ = (
    secrets_pki_dashboard,
    *secrets_pages,
    *pki_pages,
)
