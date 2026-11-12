"""Tests for PNG/APNG format detection."""

from pathlib import Path

from compressor.png import PNG_SIGNATURE, is_animated, palette_size


def _chunk(kind: bytes, payload: bytes = b"") -> bytes:
    return len(payload).to_bytes(4, "big") + kind + payload + b"\0\0\0\0"


def test_apng_animation_control_chunk_is_detected(tmp_path: Path) -> None:
    image = tmp_path / "animated.png"
    image.write_bytes(PNG_SIGNATURE + _chunk(b"IHDR") + _chunk(b"acTL", b"\0" * 8))

    assert is_animated(image)


def test_static_png_is_not_animated(tmp_path: Path) -> None:
    image = tmp_path / "static.png"
    image.write_bytes(PNG_SIGNATURE + _chunk(b"IHDR") + _chunk(b"IDAT"))

    assert not is_animated(image)


def test_palette_entry_count_is_detected(tmp_path: Path) -> None:
    image = tmp_path / "palette.png"
    image.write_bytes(
        PNG_SIGNATURE
        + _chunk(b"IHDR")
        + _chunk(b"PLTE", b"\0" * (32 * 3))
        + _chunk(b"IDAT")
    )

    assert palette_size(image) == 32
