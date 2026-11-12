"""MozJPEG compression backend."""

from __future__ import annotations

from pathlib import Path

from .models import CompressionOptions
from .utils import RetainOriginal, require_executable, run_command, temporary_output

IJG_LUMA_Q50 = (
    16, 11, 10, 16, 24, 40, 51, 61,
    12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77,
    24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101,
    72, 92, 95, 98, 112, 100, 103, 99,
)
IJG_CHROMA_Q50 = (
    17, 18, 24, 47, 99, 99, 99, 99,
    18, 21, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99,
    47, 66, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
)


def _table_quality(table: tuple[int, ...], reference: tuple[int, ...]) -> int | None:
    ratios = sorted(
        ref / value
        for ref, value in zip(reference, table, strict=True)
        if 0 < ref < 99 and value > 0
    )
    if not ratios:
        return None
    median = ratios[len(ratios) // 2]
    quality = (
        round(50 + 50 * (1 - 1 / median))
        if median >= 1
        else round(50 * median)
    )
    return max(1, min(100, quality))


def estimate_quality(source: Path) -> int | None:
    """Estimate IJG JPEG quality from embedded DQT quantization tables."""

    try:
        data = source.read_bytes()
    except OSError:
        return None

    tables: dict[int, tuple[int, ...]] = {}
    index = 0
    while index + 4 <= len(data):
        marker = data.find(b"\xff", index)
        if marker < 0 or marker + 1 >= len(data):
            break
        marker_type = data[marker + 1]
        if marker_type == 0xDA:
            break
        if marker_type != 0xDB or marker + 4 > len(data):
            index = marker + 2
            continue

        segment_length = int.from_bytes(data[marker + 2 : marker + 4], "big")
        segment_end = min(len(data), marker + 2 + segment_length)
        offset = marker + 4
        while offset < segment_end:
            descriptor = data[offset]
            precision = descriptor >> 4
            table_id = descriptor & 0x0F
            value_width = 1 if precision == 0 else 2
            table_end = offset + 1 + 64 * value_width
            if table_end > segment_end:
                break
            if value_width == 1:
                tables[table_id] = tuple(data[offset + 1 : table_end])
            offset = table_end
        index = segment_end

    luma = tables.get(0)
    if luma is None:
        return None
    luma_quality = _table_quality(luma, IJG_LUMA_Q50)
    if luma_quality is None:
        return None
    chroma = tables.get(1)
    if chroma is None:
        return luma_quality
    chroma_quality = _table_quality(chroma, IJG_CHROMA_Q50)
    if chroma_quality is None:
        return luma_quality
    return round((2 * luma_quality + chroma_quality) / 3)


def compress(source: Path, candidate: Path, options: CompressionOptions) -> None:
    """Decode and recompress a JPEG with MozJPEG.

    ``djpeg`` is required because ``cjpeg`` is an encoder and cannot read a
    JPEG source directly. Re-encoding necessarily discards source metadata.
    """

    if options.adaptive:
        estimated_quality = estimate_quality(source)
        if estimated_quality is not None and estimated_quality <= options.quality:
            raise RetainOriginal(
                f"source JPEG quality {estimated_quality} is already at or below "
                f"target {options.quality}"
            )

    djpeg = require_executable("djpeg")
    cjpeg = require_executable("cjpeg")
    jpegtran = require_executable("jpegtran")
    decoded = temporary_output(candidate, suffix=".ppm")
    encoded = temporary_output(candidate, suffix=".jpg")

    try:
        run_command([djpeg, "-outfile", str(decoded), str(source)])
        encode_command = [
            cjpeg,
            "-quality",
            str(options.quality),
            "-optimize",
            "-sample",
            "2x2,1x1,1x1",
        ]
        if options.adaptive:
            encode_command.extend(["-baseline", "-quant-table", "3"])
        else:
            encode_command.extend(["-progressive", "-trellis"])
        encode_command.extend(["-outfile", str(encoded), str(decoded)])
        run_command(encode_command)

        transform_command = [
            jpegtran,
            "-copy",
            "none",
            "-optimize",
        ]
        if not options.adaptive:
            transform_command.append("-progressive")
        transform_command.extend(["-outfile", str(candidate), str(encoded)])
        run_command(transform_command)
    finally:
        decoded.unlink(missing_ok=True)
        encoded.unlink(missing_ok=True)
