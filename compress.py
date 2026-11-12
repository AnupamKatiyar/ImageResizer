#!/usr/bin/env python3
"""Compatibility entry point for direct script execution."""

from compressor.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
