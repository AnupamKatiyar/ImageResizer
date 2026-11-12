"""WebP compression backend using cwebp."""

from __future__ import annotations

from pathlib import Path

from .models import CompressionOptions
from .utils import RetainOriginal, require_executable, run_command


def is_animated(source: Path) -> bool:
    """Return whether a WebP RIFF container includes animation chunks."""

    try:
        data = source.read_bytes()
    except OSError:
        return False
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return False
    offset = 12
    while offset + 8 <= len(data):
        chunk_type = data[offset : offset + 4]
        chunk_size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        if chunk_type in {b"ANIM", b"ANMF"}:
            return True
        offset += 8 + chunk_size + (chunk_size & 1)
    return False


def compress(source: Path, candidate: Path, options: CompressionOptions) -> None:
    """Re-encode a still WebP image at the requested quality."""

    if options.adaptive and is_animated(source):
        raise RetainOriginal(
            "animated WebP retained unchanged; cwebp only supports still images"
        )
    cwebp = require_executable("cwebp")
    command = [
        cwebp,
        "-quiet",
        "-q",
        str(options.quality),
        "-m",
        "4" if options.adaptive else "6",
    ]
    if options.adaptive:
        command.extend(["-pass", "2"])
    if not options.strip_metadata and not options.adaptive:
        command.extend(["-metadata", "all"])
    command.extend([str(source), "-o", str(candidate)])
    run_command(command)
