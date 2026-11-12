"""SVG optimization backend using SVGO."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from .models import CompressionOptions
from .utils import require_executable, run_command


def compress(source: Path, candidate: Path, options: CompressionOptions) -> None:
    """Optimize SVG markup while explicitly preserving its viewBox."""

    del options
    svgo = require_executable("svgo")
    config = files("compressor").joinpath("svgo.config.mjs")
    run_command(
        [
            svgo,
            "--input",
            str(source),
            "--output",
            str(candidate),
            "--config",
            str(config),
        ]
    )
