"""Tests for command-line validation and hierarchy discovery."""

import argparse
from pathlib import Path

from compressor.cli import (
    _discover,
    _normalized_extensions,
    _resolve_workers,
    _validate_paths,
    build_parser,
)
from compressor.models import CompressionOptions


def test_parser_accepts_documented_invocation() -> None:
    args = build_parser().parse_args(
        [
            "--input",
            "~/Pictures",
            "--output",
            "~/Pictures_Compressed",
            "--quality",
            "82",
            "--workers",
            "12",
            "--overwrite",
            "--no-adaptive",
            "--extensions",
            "jpg",
            "png",
        ]
    )

    assert isinstance(args, argparse.Namespace)
    assert args.quality == 82
    assert args.workers == "12"
    assert args.extensions == ["jpg", "png"]
    assert args.overwrite is True
    assert args.adaptive is False


def test_discovery_preserves_relative_paths_and_skips_unsupported(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "output"
    nested = source / "one" / "two"
    nested.mkdir(parents=True)
    image = nested / "photo.JPEG"
    image.write_bytes(b"jpeg")
    (nested / "notes.txt").write_text("skip", encoding="utf-8")
    (source / "empty").mkdir()

    tasks, directories = _discover(
        source,
        destination,
        {"jpeg"},
        CompressionOptions(),
        overwrite=False,
        dry_run=False,
    )

    assert len(tasks) == 1
    assert tasks[0].source == image
    assert tasks[0].destination == destination / "one" / "two" / "photo.JPEG"
    assert source / "empty" in directories


def test_overlapping_paths_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()

    try:
        _validate_paths(source, source / "compressed")
    except ValueError as exc:
        assert "must not overlap" in str(exc)
    else:
        raise AssertionError("overlapping paths were accepted")


def test_extension_and_worker_normalization() -> None:
    assert _normalized_extensions([".JPG", "png"]) == {"jpg", "png"}
    assert _resolve_workers("3") == 3
