"""Command-line interface and directory orchestration."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from .models import (
    CompressionOptions,
    CompressionResult,
    CompressionTask,
    ResultStatus,
)
from .stats import CompressionStats, format_file_result
from .utils import copy_unchanged, find_executable, preserve_metadata
from .worker import COMPRESSORS, PASSTHROUGH_EXTENSIONS, compress_file

DEFAULT_EXTENSIONS = (*COMPRESSORS, *sorted(PASSTHROUGH_EXTENSIONS))
DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "jpg": ("djpeg", "cjpeg", "jpegtran"),
    "jpeg": ("djpeg", "cjpeg", "jpegtran"),
    "png": ("pngquant", "oxipng"),
    "gif": ("gifsicle",),
    "webp": ("cwebp",),
    "svg": ("svgo",),
}


def quality_value(raw: str) -> int:
    """Parse an image quality in the inclusive range 1..100."""

    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("quality must be an integer") from exc
    if not 1 <= value <= 100:
        raise argparse.ArgumentTypeError("quality must be between 1 and 100")
    return value


def worker_value(raw: str) -> str:
    """Accept ``auto`` or a positive process count."""

    if raw == "auto":
        return raw
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("workers must be 'auto' or an integer") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("workers must be at least 1")
    return str(value)


def build_parser() -> argparse.ArgumentParser:
    """Build the public CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="image-compressor",
        description=(
            "Recursively compress images with native codecs while preserving "
            "the source directory hierarchy."
        ),
    )
    parser.add_argument("--input", type=Path, required=True, help="source directory")
    parser.add_argument("--output", type=Path, required=True, help="destination directory")
    parser.add_argument(
        "--quality",
        type=quality_value,
        default=82,
        help="JPEG and WebP quality (default: 82)",
    )
    parser.add_argument(
        "--workers",
        type=worker_value,
        default="auto",
        help="process count or 'auto' (default: auto)",
    )
    parser.add_argument(
        "--extensions",
        nargs="+",
        default=list(DEFAULT_EXTENSIONS),
        metavar="EXT",
        help=(
            "extensions to process "
            "(default: jpg jpeg png gif webp svg heic heif avif)"
        ),
    )
    parser.add_argument("--overwrite", action="store_true", help="replace existing outputs")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run codecs and report projected savings without writing outputs",
    )
    parser.add_argument(
        "--lossless-png",
        action="store_true",
        help="skip pngquant and optimize PNGs losslessly with oxipng",
    )
    parser.add_argument(
        "--strip-metadata",
        action="store_true",
        help=(
            "discard supported metadata "
            "(adaptive, PNG, and JPEG pipelines already strip it)"
        ),
    )
    parser.add_argument(
        "--adaptive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "use content-aware quality and savings guards "
            "(default: enabled; disable with --no-adaptive)"
        ),
    )
    return parser


def _normalized_extensions(raw_extensions: list[str]) -> set[str]:
    extensions = {item.lower().lstrip(".") for item in raw_extensions}
    supported = set(COMPRESSORS).union(PASSTHROUGH_EXTENSIONS)
    invalid = sorted(extensions.difference(supported))
    if invalid:
        raise ValueError(f"unsupported --extensions value(s): {', '.join(invalid)}")
    return extensions


def _resolve_workers(raw_workers: str) -> int:
    if raw_workers == "auto":
        return os.cpu_count() or 1
    return int(raw_workers)


def _validate_paths(source: Path, destination: Path) -> tuple[Path, Path]:
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"input is not a readable directory: {source}")
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("input and output directories must not overlap")
    return source, destination


def _discover(
    source: Path,
    destination: Path,
    extensions: set[str],
    options: CompressionOptions,
    *,
    overwrite: bool,
    dry_run: bool,
) -> tuple[list[CompressionTask], list[Path]]:
    tasks: list[CompressionTask] = []
    directories = [source]
    for path in source.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_dir():
            directories.append(path)
            continue
        if not path.is_file() or path.suffix.lower().lstrip(".") not in extensions:
            continue
        relative = path.relative_to(source)
        tasks.append(
            CompressionTask(
                source=path,
                destination=destination / relative,
                options=options,
                overwrite=overwrite,
                dry_run=dry_run,
            )
        )
    tasks.sort(key=lambda task: str(task.source))
    return tasks, directories


def _prepare_directories(
    source: Path,
    destination: Path,
    directories: list[Path],
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for directory in directories:
        relative = directory.relative_to(source)
        (destination / relative).mkdir(parents=True, exist_ok=True)


def _restore_directory_metadata(
    source: Path,
    destination: Path,
    directories: list[Path],
) -> None:
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        preserve_metadata(directory, destination / directory.relative_to(source))


def _missing_tools(extensions: set[str], *, lossless_png: bool) -> list[str]:
    required: set[str] = set()
    for extension in extensions:
        required.update(DEPENDENCIES.get(extension, ()))
    if lossless_png:
        required.discard("pngquant")
    return sorted(tool for tool in required if find_executable(tool) is None)


def _unexpected_failure(task: CompressionTask, exc: Exception) -> CompressionResult:
    try:
        original_size = task.source.stat().st_size
    except OSError:
        original_size = 0
    message = f"worker terminated unexpectedly: {exc}"
    if not task.dry_run:
        try:
            copy_unchanged(task.source, task.destination)
        except OSError as copy_exc:
            message = f"{message}; fallback copy failed: {copy_exc}"
    return CompressionResult(
        source=task.source,
        destination=task.destination,
        status=ResultStatus.FAILED,
        original_size=original_size,
        output_size=original_size,
        elapsed_seconds=0.0,
        message=message,
    )


def _process(tasks: list[CompressionTask], workers: int) -> CompressionStats:
    stats = CompressionStats()
    if not tasks:
        return stats
    with ProcessPoolExecutor(max_workers=min(workers, len(tasks))) as executor:
        futures: dict[Future[CompressionResult], CompressionTask] = {
            executor.submit(compress_file, task): task for task in tasks
        }
        with tqdm(total=len(tasks), unit="file", desc="Compressing") as progress:
            for future in as_completed(futures):
                task = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = _unexpected_failure(task, exc)
                stats.add(result)
                tqdm.write(format_file_result(result))
                progress.update()
    return stats


def _write_failure_log(results: list[CompressionResult], log_path: Path) -> None:
    failures = [result for result in results if result.status is ResultStatus.FAILED]
    if not failures:
        log_path.unlink(missing_ok=True)
        return
    logger = logging.getLogger("image-compressor.failures")
    logger.setLevel(logging.ERROR)
    logger.propagate = False
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s\t%(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    try:
        for result in failures:
            logger.error("%s\t%s", result.source, result.message)
    finally:
        handler.close()
        logger.removeHandler(handler)


def run(args: argparse.Namespace) -> int:
    """Execute a validated compression run and return a process exit code."""

    try:
        source, destination = _validate_paths(args.input, args.output)
        extensions = _normalized_extensions(args.extensions)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    workers = _resolve_workers(args.workers)
    options = CompressionOptions(
        quality=args.quality,
        lossless_png=args.lossless_png,
        strip_metadata=args.strip_metadata,
        adaptive=args.adaptive,
    )
    tasks, directories = _discover(
        source,
        destination,
        extensions,
        options,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )

    active_extensions = {
        task.source.suffix.lower().lstrip(".") for task in tasks
    }
    missing = _missing_tools(active_extensions, lossless_png=args.lossless_png)
    if missing:
        print(
            "warning: missing native tools; affected files will be copied unchanged: "
            + ", ".join(missing),
            file=sys.stderr,
        )
    if not args.dry_run:
        _prepare_directories(source, destination, directories)

    started = time.perf_counter()
    try:
        stats = _process(tasks, workers)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    elapsed = time.perf_counter() - started

    if not args.dry_run:
        _restore_directory_metadata(source, destination, directories)
    failure_log = destination.parent / f"{destination.name}.failures.log"
    if not args.dry_run:
        _write_failure_log(stats.results, failure_log)

    print(stats.format_report(elapsed))
    if stats.failures:
        if not args.dry_run:
            print(f"\nFailure log: {failure_log}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and run the application."""

    parser = build_parser()
    return run(parser.parse_args(argv))
