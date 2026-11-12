"""Process-pool worker entry point and codec dispatch."""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from . import gif, jpeg, png, svg, webp
from .models import (
    CompressionOptions,
    CompressionResult,
    CompressionTask,
    ResultStatus,
)
from .utils import (
    CompressionError,
    RetainOriginal,
    copy_unchanged,
    install_candidate,
    temporary_output,
)

Compressor = Callable[[Path, Path, CompressionOptions], None]

COMPRESSORS: dict[str, Compressor] = {
    "jpg": jpeg.compress,
    "jpeg": jpeg.compress,
    "png": png.compress,
    "gif": gif.compress,
    "webp": webp.compress,
    "svg": svg.compress,
}
PASSTHROUGH_EXTENSIONS = frozenset({"heic", "heif", "avif"})


def compress_file(task: CompressionTask) -> CompressionResult:
    """Compress one file, retaining the original when compression fails."""

    started = time.perf_counter()
    try:
        original_size = task.source.stat().st_size
    except OSError as exc:
        return CompressionResult(
            source=task.source,
            destination=task.destination,
            status=ResultStatus.FAILED,
            original_size=0,
            output_size=0,
            elapsed_seconds=time.perf_counter() - started,
            message=f"could not stat source: {exc}",
        )

    if task.destination.exists() and not task.overwrite and not task.dry_run:
        return CompressionResult(
            source=task.source,
            destination=task.destination,
            status=ResultStatus.SKIPPED,
            original_size=original_size,
            output_size=original_size,
            elapsed_seconds=time.perf_counter() - started,
            message="destination exists (use --overwrite to replace it)",
        )

    extension = task.source.suffix.lower().lstrip(".")
    if extension in PASSTHROUGH_EXTENSIONS:
        try:
            if not task.dry_run:
                copy_unchanged(task.source, task.destination)
        except OSError as exc:
            return CompressionResult(
                source=task.source,
                destination=task.destination,
                status=ResultStatus.FAILED,
                original_size=original_size,
                output_size=original_size,
                elapsed_seconds=time.perf_counter() - started,
                message=f"passthrough copy failed: {exc}",
            )
        return CompressionResult(
            source=task.source,
            destination=task.destination,
            status=ResultStatus.RETAINED,
            original_size=original_size,
            output_size=original_size,
            elapsed_seconds=time.perf_counter() - started,
            message="copied unchanged (codec support not enabled)",
        )

    compressor = COMPRESSORS.get(extension)
    if compressor is None:
        return CompressionResult(
            source=task.source,
            destination=task.destination,
            status=ResultStatus.SKIPPED,
            original_size=original_size,
            output_size=original_size,
            elapsed_seconds=time.perf_counter() - started,
            message=f"unsupported extension: .{extension}",
        )

    candidate: Path | None = None
    temporary_directory: tempfile.TemporaryDirectory[str] | None = None
    try:
        if task.dry_run:
            temporary_directory = tempfile.TemporaryDirectory(prefix="image-compressor-")
            candidate = Path(temporary_directory.name) / f"candidate{task.source.suffix}"
            candidate.touch()
        else:
            candidate = temporary_output(task.destination, suffix=task.source.suffix)

        compressor(task.source, candidate, task.options)
        if not candidate.is_file() or candidate.stat().st_size == 0:
            raise CompressionError("compressor produced an empty output")

        output_size, used_candidate = install_candidate(
            candidate,
            task.source,
            task.destination,
            dry_run=task.dry_run,
            minimum_saving_ratio=(
                0.03 if task.options.adaptive and extension == "gif" else 0.0
            ),
        )
        return CompressionResult(
            source=task.source,
            destination=task.destination,
            status=(
                ResultStatus.COMPRESSED if used_candidate else ResultStatus.RETAINED
            ),
            original_size=original_size,
            output_size=output_size,
            elapsed_seconds=time.perf_counter() - started,
            message=(
                ""
                if used_candidate
                else "compressed output did not meet the savings threshold"
            ),
        )
    except RetainOriginal as exc:
        message = str(exc) or "adaptive guard retained the original"
        if not task.dry_run:
            try:
                copy_unchanged(task.source, task.destination)
            except OSError as copy_exc:
                return CompressionResult(
                    source=task.source,
                    destination=task.destination,
                    status=ResultStatus.FAILED,
                    original_size=original_size,
                    output_size=original_size,
                    elapsed_seconds=time.perf_counter() - started,
                    message=f"{message}; fallback copy failed: {copy_exc}",
                )
        return CompressionResult(
            source=task.source,
            destination=task.destination,
            status=ResultStatus.RETAINED,
            original_size=original_size,
            output_size=original_size,
            elapsed_seconds=time.perf_counter() - started,
            message=message,
        )
    except Exception as exc:
        message = str(exc) or type(exc).__name__
        if not task.dry_run:
            try:
                copy_unchanged(task.source, task.destination)
            except OSError as copy_exc:
                message = f"{message}; fallback copy failed: {copy_exc}"
        return CompressionResult(
            source=task.source,
            destination=task.destination,
            status=ResultStatus.FAILED,
            original_size=original_size,
            output_size=original_size,
            elapsed_seconds=time.perf_counter() - started,
            message=message,
        )
    finally:
        if candidate is not None:
            candidate.unlink(missing_ok=True)
        if temporary_directory is not None:
            temporary_directory.cleanup()
