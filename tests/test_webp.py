"""Tests for animated WebP detection."""

from pathlib import Path

from compressor.webp import is_animated


def _webp(chunks: bytes) -> bytes:
    return b"RIFF" + (len(chunks) + 4).to_bytes(4, "little") + b"WEBP" + chunks


def _chunk(kind: bytes, payload: bytes = b"") -> bytes:
    padding = b"\0" if len(payload) % 2 else b""
    return kind + len(payload).to_bytes(4, "little") + payload + padding


def test_animation_chunk_is_detected(tmp_path: Path) -> None:
    image = tmp_path / "animated.webp"
    image.write_bytes(_webp(_chunk(b"ANIM", b"\0" * 6)))

    assert is_animated(image)


def test_still_webp_is_not_animated(tmp_path: Path) -> None:
    image = tmp_path / "still.webp"
    image.write_bytes(_webp(_chunk(b"VP8 ", b"\0" * 4)))

    assert not is_animated(image)
