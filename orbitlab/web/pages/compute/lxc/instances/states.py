"""OrbitLab LXC States."""

import reflex as rx


class LXCInstancesTableState(rx.State):
    """State management for running LXC containers."""

    instance_to_terminate: str = ""



class LaunchLXCInstanceDialogState(rx.State):
    """State management for launching LXC instances."""

    form_data: rx.Field[dict] = rx.field(default_factory=dict)
