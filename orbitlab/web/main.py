"""OrbitLab Web UI."""
import reflex as rx

from .compute import *  # noqa: F403
from .nodes import *  # noqa: F403

app = rx.App(
    stylesheets=["animations.css"],
)
