"""State management for Proxmox nodes."""

import reflex as rx

from .manifests import ManifestsState


class ProxmoxNodesState(ManifestsState):
    """State management for Proxmox nodes."""

    refresh_nodes: rx.Field[bool] = False
    refresh_rate: rx.Field[int] = 10
