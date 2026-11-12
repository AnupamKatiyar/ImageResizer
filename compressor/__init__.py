"""Native-codec directory image compressor."""

from .models import CompressionOptions, CompressionResult, CompressionTask, ResultStatus

__all__ = [
    "CompressionOptions",
    "CompressionResult",
    "CompressionTask",
    "ResultStatus",
]

__version__ = "1.1.0"
