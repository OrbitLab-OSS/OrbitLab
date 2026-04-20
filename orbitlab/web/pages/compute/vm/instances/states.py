"""OrbitLab VM Instances States."""

import reflex as rx

from orbitlab.web.global_state import OrbitLabState


class VMInstancesTableState(OrbitLabState):
    """State management for running VMs."""

    instance_to_terminate: rx.Field[str] = rx.field(default="")


class LaunchVMDialogState(rx.State):
    """State management for the Launch VM dialog."""

    form_data: rx.Field[dict] = rx.field(default_factory=dict)
