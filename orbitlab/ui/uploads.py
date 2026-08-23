"""Temporary build-file storage used by NiceGUI template forms."""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from pathlib import Path
import tempfile
from uuid import uuid4

from orbitlab.redis import models


@dataclass(slots=True)
class UploadedBuildFile:
    """An uploaded file and the absolute guest path selected by the operator."""

    source: Path
    filename: str
    destination: Path

    def as_workflow_file(self) -> models.File:
        """Validate the destination before serializing a workflow file step."""
        if not self.destination.is_absolute() or ".." in self.destination.parts:
            raise ValueError(f"Destination for '{self.filename}' must be a safe absolute guest path.")
        return models.File(source=self.source, destination=self.destination)


class BuildUploadStore:
    """Stores browser uploads outside the application package for one build job."""

    def __init__(self) -> None:
        root = Path(os.environ.get("ORBITLAB_UPLOAD_DIR", Path(tempfile.gettempdir()) / "orbitlab" / "uploads"))
        self._directory = root / uuid4().hex

    async def save(self, upload: object) -> UploadedBuildFile:
        """Persist one NiceGUI upload and return its typed workflow representation."""
        filename = Path(str(getattr(upload, "name"))).name
        if not filename or filename in {".", ".."}:
            raise ValueError("Uploaded files require a valid filename.")
        self._directory.mkdir(parents=True, exist_ok=True)
        content = getattr(upload, "content").read()
        if inspect.isawaitable(content):
            content = await content
        source = self._directory / filename
        source.write_bytes(content)
        return UploadedBuildFile(source=source, filename=filename, destination=Path(f"/root/{filename}"))
