"""Compute Instance Manifests."""

from .lxc import LXCManifest
from .vm import VMManifest

__all__ = ("LXCManifest", "VMManifest")
