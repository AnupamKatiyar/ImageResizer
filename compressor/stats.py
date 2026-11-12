"""Compression statistics collection and terminal rendering."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import CompressionResult, ResultStatus

MEBIBYTE = 1024 * 1024


@dataclass(slots=True)
class CompressionStats:
    """Aggregate compression outcomes and produce a concise report."""

    results: list[CompressionResult] = field(default_factory=list)

    def add(self, result: CompressionResult) -> None:
        """Add one worker result."""

        self.results.append(result)

    @property
    def original_size(self) -> int:
        """Return total source bytes considered."""

        return sum(result.original_size for result in self.results)

    @property
    def output_size(self) -> int:
        """Return effective total output bytes."""

        return sum(result.output_size for result in self.results)

    @property
    def bytes_saved(self) -> int:
        """Return total non-negative savings."""

        return sum(result.bytes_saved for result in self.results)

    @property
    def saving_percent(self) -> float:
        """Return aggregate percentage saved."""

        if self.original_size == 0:
            return 0.0
        return self.bytes_saved * 100.0 / self.original_size

    @property
    def failures(self) -> list[CompressionResult]:
        """Return failed file results."""

        return [
            result for result in self.results if result.status is ResultStatus.FAILED
        ]

    def largest_reductions(self, limit: int = 10) -> list[CompressionResult]:
        """Return files ordered by absolute byte reduction."""

        reduced = [result for result in self.results if result.bytes_saved > 0]
        return sorted(reduced, key=lambda result: result.bytes_saved, reverse=True)[:limit]

    def format_report(self, elapsed_seconds: float) -> str:
        """Render final aggregate metrics and largest reductions."""

        speed = (
            self.original_size / MEBIBYTE / elapsed_seconds
            if elapsed_seconds > 0
            else 0.0
        )
        lines = [
            "",
            "Compression summary",
            f"  Original size:     {self.original_size / MEBIBYTE:,.2f} MB",
            f"  Compressed size:   {self.output_size / MEBIBYTE:,.2f} MB",
            f"  Saved:             {self.bytes_saved / MEBIBYTE:,.2f} MB",
            f"  Saved percentage:  {self.saving_percent:.2f}%",
            f"  Total files:       {len(self.results):,}",
            f"  Failed files:      {len(self.failures):,}",
            f"  Time taken:        {elapsed_seconds:.2f} s",
            f"  Compression speed: {speed:.2f} MB/s",
        ]

        largest = self.largest_reductions()
        if largest:
            lines.extend(["", "Largest reductions"])
            for result in largest:
                lines.append(
                    f"  {result.source}: "
                    f"{result.bytes_saved / MEBIBYTE:,.2f} MB "
                    f"({result.saving_percent:.1f}%)"
                )
        return "\n".join(lines)


def format_file_result(result: CompressionResult) -> str:
    """Render a one-line result for an individual file."""

    return (
        f"{result.status.value:10} {result.source} — "
        f"saved {result.bytes_saved / MEBIBYTE:,.2f} MB "
        f"({result.saving_percent:.1f}%)"
        + (f" [{result.message}]" if result.message else "")
    )
