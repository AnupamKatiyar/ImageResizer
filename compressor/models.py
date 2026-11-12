"""Shared immutable data models for compression jobs and results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ResultStatus(StrEnum):
    """Possible outcomes for one input file."""

    COMPRESSED = "compressed"
    RETAINED = "retained"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CompressionOptions:
    """Options used by native image compressors."""

    quality: int = 82
    lossless_png: bool = False
    strip_metadata: bool = False
    adaptive: bool = True


@dataclass(frozen=True, slots=True)
class CompressionTask:
    """A serializable unit of work submitted to a worker process."""

    source: Path
    destination: Path
    options: CompressionOptions
    overwrite: bool = False
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class CompressionResult:
    """The result and size accounting for one source file."""

    source: Path
    destination: Path
    status: ResultStatus
    original_size: int
    output_size: int
    elapsed_seconds: float
    message: str = ""

    @property
    def bytes_saved(self) -> int:
        """Return non-negative bytes saved by this operation."""

        return max(0, self.original_size - self.output_size)

    @property
    def saving_percent(self) -> float:
        """Return the percentage reduction from the original."""

        if self.original_size == 0:
            return 0.0
        return self.bytes_saved * 100.0 / self.original_size
