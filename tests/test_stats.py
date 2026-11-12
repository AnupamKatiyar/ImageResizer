"""Tests for aggregate compression statistics."""

from pathlib import Path

from compressor.models import CompressionResult, ResultStatus
from compressor.stats import CompressionStats


def _result(name: str, original: int, output: int) -> CompressionResult:
    path = Path(name)
    return CompressionResult(
        source=path,
        destination=Path("out") / path,
        status=ResultStatus.COMPRESSED,
        original_size=original,
        output_size=output,
        elapsed_seconds=0.1,
    )


def test_aggregate_sizes_and_largest_reductions() -> None:
    stats = CompressionStats(
        [
            _result("small.jpg", 100, 80),
            _result("large.png", 1_000, 400),
        ]
    )

    assert stats.original_size == 1_100
    assert stats.output_size == 480
    assert stats.bytes_saved == 620
    assert stats.largest_reductions(1)[0].source == Path("large.png")
    assert "Total files:       2" in stats.format_report(1.0)
