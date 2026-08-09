#!/usr/bin/env python3
"""Recalculate quality and deprecation metadata for the bundled prompt corpus."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import apply_deprecation_flags, apply_quality_scores, log


def main() -> int:
    scored = apply_quality_scores()
    deprecated = apply_deprecation_flags()
    log(f"Quality scores recalculated for {scored} records")
    log(f"Deprecation metadata changed for {deprecated} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
