#!/usr/bin/env python3
"""Parley CLI entrypoint (thin shim).

The implementation lives in the `parley` package (core / adapters / workflows).
This file is kept at the repo root so existing invocations like
`python3 parley.py <command>` continue to work unchanged.
"""

import os
import sys

# Ensure the repo root (this file's directory) is importable so the
# `parley` package resolves regardless of the current working directory.
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from parley.cli import main

if __name__ == "__main__":
    main()
