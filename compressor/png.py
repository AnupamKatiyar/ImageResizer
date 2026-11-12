"""PNG compression backend using pngquant and oxipng."""

from __future__ import annotations

from pathlib import Path

from .models import CompressionOptions
from .utils import (
    CompressionError,
    RetainOriginal,
    require_executable,
    run_command,
    temporary_output,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def is_animated(source: Path) -> bool:
    """Return whether a PNG contains an APNG animation control chunk."""

    try:
        with source.open("rb") as stream:
            if stream.read(8) != PNG_SIGNATURE:
                return False
            while True:
                length_bytes = stream.read(4)
                chunk_type = stream.read(4)
                if len(length_bytes) != 4 or len(chunk_type) != 4:
                    return False
                if chunk_type == b"acTL":
                    return True
                if chunk_type in {b"IDAT", b"IEND"}:
                    return False
                stream.seek(int.from_bytes(length_bytes, "big") + 4, 1)
    except OSError:
        return False


def palette_size(source: Path) -> int | None:
    """Return the number of PLTE entries, or ``None`` for truecolor PNGs."""

    try:
        with source.open("rb") as stream:
            if stream.read(8) != PNG_SIGNATURE:
                return None
            while True:
                length_bytes = stream.read(4)
                chunk_type = stream.read(4)
                if len(length_bytes) != 4 or len(chunk_type) != 4:
                    return None
                length = int.from_bytes(length_bytes, "big")
                if chunk_type == b"PLTE":
                    return length // 3
                if chunk_type in {b"IDAT", b"IEND"}:
                    return None
                stream.seek(length + 4, 1)
    except OSError:
        return None


def compress(source: Path, candidate: Path, options: CompressionOptions) -> None:
    """Compress a PNG, optionally bypassing the lossy quantization stage."""

    oxipng = require_executable("oxipng")
    animated = is_animated(source)
    existing_palette = palette_size(source)
    if (
        options.adaptive
        and not options.lossless_png
        and existing_palette is not None
        and existing_palette < 256
    ):
        raise RetainOriginal(
            f"source PNG already uses a {existing_palette}-color palette"
        )
    quantized: Path | None = None
    stage_input = source

    try:
        if not options.lossless_png and not animated:
            pngquant = require_executable("pngquant")
            quantized = temporary_output(candidate, suffix=".png")
            try:
                run_command(
                    [
                        pngquant,
                        "--force",
                        "--output",
                        str(quantized),
                        "--quality",
                        "0-99" if options.adaptive else "70-95",
                        "--speed",
                        "1",
                        "--nofs",
                        "--",
                        str(source),
                    ]
                )
                stage_input = quantized
            except CompressionError as exc:
                # pngquant uses 99 when its minimum quality cannot be met.
                # A lossless oxipng pass can still reduce the original.
                if "status 99" not in str(exc):
                    raise

        run_command(
            [
                oxipng,
                "--opt",
                "4",
                "--strip",
                "safe" if animated else "all",
                "--force",
                "--out",
                str(candidate),
                str(stage_input),
            ]
        )
    finally:
        if quantized is not None:
            quantized.unlink(missing_ok=True)
