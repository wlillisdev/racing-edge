"""IMPORT SMOKE — every module in the package imports (audit 2026-09-02).

A crash at import time happens BEFORE run_guarded's crash net (cli/_common.py)
can email anyone; the only trace is a traceback in the flight recorder. This
test makes the suite — and CI, before the box pulls — the place such a crash
is caught."""

from __future__ import annotations

import importlib
import pkgutil

import racing_edge


def test_every_module_imports() -> None:
    failed = []
    for m in pkgutil.walk_packages(racing_edge.__path__, "racing_edge."):
        try:
            importlib.import_module(m.name)
        except Exception as exc:          # noqa: BLE001 — the point is to name it
            failed.append(f"{m.name}: {exc.__class__.__name__}: {exc}")
    assert not failed, "modules that do not import:\n" + "\n".join(failed)
