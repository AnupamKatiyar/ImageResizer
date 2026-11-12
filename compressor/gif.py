"""GIF compression backend using gifsicle."""

from __future__ import annotations

from pathlib import Path

from .models import CompressionOptions
from .utils import require_executable, run_command


def compress(source: Path, candidate: Path, options: CompressionOptions) -> None:
    """Optimize a GIF while preserving animation control extensions."""

    del options
    gifsicle = require_executable("gifsicle")
    run_command(
        [
            gifsicle,
            "-O3",
            "--no-comments",
            "--no-names",
            "--output",
            str(candidate),
            str(source),
        ]
    )
