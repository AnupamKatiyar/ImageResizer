"""Filesystem and subprocess helpers used by compression backends."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

MOZJPEG_TOOLS = frozenset({"cjpeg", "djpeg", "jpegtran"})


class CompressionError(RuntimeError):
    """Raised when a native compression command cannot produce an output."""


class RetainOriginal(RuntimeError):
    """Signal that an adaptive guard selected the original file."""


def find_executable(name: str) -> str | None:
    """Find a codec, preferring a keg-only Homebrew MozJPEG installation."""

    if name in MOZJPEG_TOOLS:
        custom_bin = os.environ.get("MOZJPEG_BIN")
        search_roots = [
            Path(custom_bin) if custom_bin else None,
            Path("/opt/homebrew/opt/mozjpeg/bin"),
            Path("/usr/local/opt/mozjpeg/bin"),
        ]
        for root in search_roots:
            if root is not None:
                candidate = root / name
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return str(candidate)
    return shutil.which(name)


def require_executable(name: str) -> str:
    """Return the absolute executable path or raise a useful error."""

    executable = find_executable(name)
    if executable is None:
        raise CompressionError(
            f"required executable '{name}' was not found on PATH"
        )
    return executable


def run_command(args: Sequence[str], *, timeout: float = 600.0) -> None:
    """Run a native compressor and raise a concise error on failure."""

    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise CompressionError(
            f"{Path(args[0]).name} timed out after {timeout:g} seconds"
        ) from exc
    except OSError as exc:
        raise CompressionError(f"could not run {Path(args[0]).name}: {exc}") from exc

    if completed.returncode != 0:
        detail_bytes = completed.stderr.strip() or completed.stdout.strip()
        detail = detail_bytes.decode("utf-8", errors="replace")
        if len(detail) > 500:
            detail = f"{detail[:497]}..."
        suffix = f": {detail}" if detail else ""
        raise CompressionError(
            f"{Path(args[0]).name} exited with status {completed.returncode}{suffix}"
        )


def temporary_output(destination: Path, *, suffix: str) -> Path:
    """Create an empty temporary file beside the final output."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=suffix,
        dir=destination.parent,
    )
    os.close(descriptor)
    return Path(raw_path)


def preserve_metadata(source: Path, destination: Path) -> None:
    """Best-effort copy of mode bits and filesystem timestamps."""

    try:
        shutil.copystat(source, destination, follow_symlinks=False)
    except OSError:
        # Compression should still succeed on filesystems that cannot preserve
        # ownership-adjacent metadata or nanosecond timestamps.
        with suppress(OSError):
            os.chmod(destination, source.stat(follow_symlinks=False).st_mode)


def copy_unchanged(source: Path, destination: Path) -> None:
    """Atomically copy a source file and preserve its metadata."""

    temporary = temporary_output(destination, suffix=source.suffix)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def install_candidate(
    candidate: Path,
    source: Path,
    destination: Path,
    *,
    dry_run: bool,
    minimum_saving_ratio: float = 0.0,
) -> tuple[int, bool]:
    """Install a meaningfully smaller candidate, otherwise retain the source.

    Returns the effective output size and whether the compressed candidate won.
    """

    original_size = source.stat().st_size
    candidate_size = candidate.stat().st_size
    saving_ratio = (
        (original_size - candidate_size) / original_size
        if original_size > 0
        else 0.0
    )
    use_candidate = candidate_size < original_size and saving_ratio > minimum_saving_ratio

    if not dry_run:
        if use_candidate:
            preserve_metadata(source, candidate)
            os.replace(candidate, destination)
        else:
            copy_unchanged(source, destination)

    return (candidate_size if use_candidate else original_size, use_candidate)
