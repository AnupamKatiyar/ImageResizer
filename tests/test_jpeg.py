"""Tests for adaptive JPEG quality detection."""

from pathlib import Path

from compressor.jpeg import IJG_CHROMA_Q50, IJG_LUMA_Q50, estimate_quality


def test_estimates_quality_from_dqt_tables(tmp_path: Path) -> None:
    source = tmp_path / "quality-50.jpg"
    payload = (
        b"\x00"
        + bytes(IJG_LUMA_Q50)
        + b"\x01"
        + bytes(IJG_CHROMA_Q50)
    )
    dqt = b"\xff\xdb" + (len(payload) + 2).to_bytes(2, "big") + payload
    source.write_bytes(b"\xff\xd8" + dqt + b"\xff\xda")

    assert estimate_quality(source) == 50


def test_returns_none_without_quantization_tables(tmp_path: Path) -> None:
    source = tmp_path / "invalid.jpg"
    source.write_bytes(b"\xff\xd8\xff\xd9")

    assert estimate_quality(source) is None
