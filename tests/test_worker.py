"""Tests for worker output selection and failure fallback."""

from pathlib import Path

from compressor.models import CompressionOptions, CompressionTask, ResultStatus
from compressor.worker import COMPRESSORS, compress_file


def _task(source: Path, destination: Path, *, dry_run: bool = False) -> CompressionTask:
    return CompressionTask(
        source=source,
        destination=destination,
        options=CompressionOptions(),
        dry_run=dry_run,
    )


def test_smaller_candidate_replaces_source_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    destination = tmp_path / "out" / "source.jpg"
    source.write_bytes(b"x" * 100)

    def fake_compressor(
        _source: Path, candidate: Path, _options: CompressionOptions
    ) -> None:
        candidate.write_bytes(b"x" * 40)

    original = COMPRESSORS["jpg"]
    COMPRESSORS["jpg"] = fake_compressor
    try:
        result = compress_file(_task(source, destination))
    finally:
        COMPRESSORS["jpg"] = original

    assert result.status is ResultStatus.COMPRESSED
    assert result.bytes_saved == 60
    assert destination.read_bytes() == b"x" * 40


def test_larger_candidate_retains_original(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    destination = tmp_path / "out" / "source.png"
    source.write_bytes(b"original")

    def fake_compressor(
        _source: Path, candidate: Path, _options: CompressionOptions
    ) -> None:
        candidate.write_bytes(b"a much larger output")

    original = COMPRESSORS["png"]
    COMPRESSORS["png"] = fake_compressor
    try:
        result = compress_file(_task(source, destination))
    finally:
        COMPRESSORS["png"] = original

    assert result.status is ResultStatus.RETAINED
    assert result.bytes_saved == 0
    assert destination.read_bytes() == b"original"


def test_failure_is_reported_and_source_is_copied(tmp_path: Path) -> None:
    source = tmp_path / "source.webp"
    destination = tmp_path / "out" / "source.webp"
    source.write_bytes(b"original")

    def broken_compressor(
        _source: Path, _candidate: Path, _options: CompressionOptions
    ) -> None:
        raise RuntimeError("codec failed")

    original = COMPRESSORS["webp"]
    COMPRESSORS["webp"] = broken_compressor
    try:
        result = compress_file(_task(source, destination))
    finally:
        COMPRESSORS["webp"] = original

    assert result.status is ResultStatus.FAILED
    assert result.message == "codec failed"
    assert destination.read_bytes() == b"original"


def test_dry_run_does_not_create_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.gif"
    destination = tmp_path / "out" / "source.gif"
    source.write_bytes(b"x" * 20)

    def fake_compressor(
        _source: Path, candidate: Path, _options: CompressionOptions
    ) -> None:
        candidate.write_bytes(b"x" * 5)

    original = COMPRESSORS["gif"]
    COMPRESSORS["gif"] = fake_compressor
    try:
        result = compress_file(_task(source, destination, dry_run=True))
    finally:
        COMPRESSORS["gif"] = original

    assert result.status is ResultStatus.COMPRESSED
    assert result.bytes_saved == 15
    assert not destination.parent.exists()


def test_heic_is_copied_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "source.heic"
    destination = tmp_path / "out" / "source.heic"
    source.write_bytes(b"heic-content")

    result = compress_file(_task(source, destination))

    assert result.status is ResultStatus.RETAINED
    assert destination.read_bytes() == b"heic-content"
    assert "copied unchanged" in result.message


def test_adaptive_gif_requires_more_than_three_percent_savings(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.gif"
    destination = tmp_path / "out" / "source.gif"
    source.write_bytes(b"x" * 100)

    def fake_compressor(
        _source: Path, candidate: Path, _options: CompressionOptions
    ) -> None:
        candidate.write_bytes(b"x" * 98)

    original = COMPRESSORS["gif"]
    COMPRESSORS["gif"] = fake_compressor
    try:
        result = compress_file(_task(source, destination))
    finally:
        COMPRESSORS["gif"] = original

    assert result.status is ResultStatus.RETAINED
    assert destination.read_bytes() == b"x" * 100
