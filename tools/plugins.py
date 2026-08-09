#!/usr/bin/env python3
"""Entry-point based plugin API for custom prompt importers."""

from __future__ import annotations

from importlib import metadata
from typing import Callable


PLUGIN_GROUP = "promptcompanion.importers"
PLUGIN_API_VERSION = 1


def _group_entries(entry_points):
    if hasattr(entry_points, "select"):
        return entry_points.select(group=PLUGIN_GROUP)
    return entry_points.get(PLUGIN_GROUP, [])


def discover_importers(entry_points=None) -> dict[str, Callable]:
    """Load installed importer entry points keyed by their declared name.

    A plugin may expose either a callable accepting ``**options`` or an object
    with a callable ``import_prompts`` method. Broken plugins are skipped so a
    single optional extension cannot prevent the built-in pipeline from loading.
    """
    if entry_points is None:
        entry_points = metadata.entry_points()
    importers: dict[str, Callable] = {}
    for entry in _group_entries(entry_points):
        try:
            loaded = entry.load()
            importer = loaded if callable(loaded) else getattr(loaded, "import_prompts")
            importers[str(entry.name)] = importer
        except (AttributeError, ImportError, TypeError):
            continue
    return importers


def run_importer(name: str, options: dict | None = None, entry_points=None):
    """Run one discovered importer and return its result."""
    importer = discover_importers(entry_points).get(name)
    if importer is None:
        raise KeyError(f"Importer plugin not found: {name}")
    return importer(**(options or {}))
