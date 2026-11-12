# image-compressor

A Python 3.12+ CLI that compresses image trees in parallel with native codecs.
It preserves filenames, relative directory structure, file modes, and timestamps.
If compression grows a file or a codec fails, the original is copied unchanged.
HEIC, HEIF, and AVIF files are copied unchanged; other unsupported files are skipped.

Adaptive compression is enabled by default. It follows the decision strategy used
by browser-local compressors: avoid recompressing JPEGs already at or below the
target quality, avoid re-quantizing small PNG palettes, require meaningful GIF
savings, and retain animated WebP files that `cwebp` cannot safely process.

## Native dependencies

The selected formats require these executables on `PATH`:

- JPEG: MozJPEG `djpeg`, `cjpeg`, and `jpegtran`
- PNG: `pngquant` and `oxipng` (`pngquant` is optional with `--lossless-png`)
- GIF: `gifsicle`
- WebP: `cwebp`
- SVG: `svgo`

`djpeg` is necessary because `cjpeg` only encodes decompressed pixel formats; it
cannot decode a JPEG source.

On macOS with Homebrew:

```shell
brew install mozjpeg pngquant oxipng gifsicle webp svgo
export PATH="$(brew --prefix mozjpeg)/bin:$PATH"
```

The CLI automatically prefers Homebrew's keg-only MozJPEG path on macOS; the
`PATH` export is still useful when invoking MozJPEG commands manually.

On Debian/Ubuntu, package names vary by release. Install MozJPEG separately if
the distribution's `libjpeg` tools are not MozJPEG builds.

## Install

```shell
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
```

For development:

```shell
python -m pip install -e '.[dev]'
pytest
ruff check .
mypy compressor compress.py
```

## Usage

```shell
image-compressor \
  --input ~/Pictures \
  --output ~/Pictures_Compressed \
  --quality 82 \
  --workers auto
```

Direct script execution is also supported:

```shell
python compress.py --input ~/Pictures --output ~/Pictures_Compressed
```

Options:

```text
--overwrite                 Replace destination files that already exist
--dry-run                   Measure projected savings without writing output
--lossless-png              Skip pngquant and use only oxipng
--strip-metadata            Strip WebP metadata when adaptive mode is disabled
--adaptive / --no-adaptive  Enable or disable content-aware guards
--extensions EXT [EXT ...]  Restrict processing to selected supported formats
--workers auto|N            Use detected CPU count or N worker processes
```

In adaptive mode:

- JPEG quality is estimated from its DQT tables. Sources already at or below the
  target are copied byte-for-byte; other JPEGs use a site-like baseline MozJPEG
  profile with optimized coding and 4:2:0 subsampling.
- PNG uses zero-dither quantization with a 0–99 quality target followed by
  OxiPNG. Existing palettes below 256 colors are retained. APNG avoids lossy
  quantization and uses animation-safe metadata stripping.
- GIF output must save more than 3%, otherwise the original is retained.
- Still WebP uses method 4 with two analysis passes. Animated WebP is retained.
- SVG optimization preserves viewBox, IDs, definitions, and three-digit numeric
  precision for sprite safety.

Use `--no-adaptive` for the original fixed profiles: progressive/trellis JPEG,
PNG quality 70–95, method-6 WebP, and acceptance of any smaller GIF output.

The command prints each file's savings, a tqdm progress bar, aggregate sizes,
elapsed time, throughput, and the largest reductions. Failures do not stop the
run and are written beside the output directory to
`<output-directory-name>.failures.log`. A run with failures exits with status 1.

Input and output directories may not overlap. Symbolic links are skipped to
avoid traversing or copying content outside the requested input tree.
