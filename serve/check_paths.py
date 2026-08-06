#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка путей registry/tokenizer без загрузки GPU-модели."""
from __future__ import annotations

import sys
from pathlib import Path

SERVE = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVE))

from app.engine import get_engine  # noqa: E402


def main() -> int:
    eng = get_engine()
    h = eng.health()
    print("project_root:", h["project_root"])
    print("tokenizer:", h["tokenizer_path"], "exists=", h["tokenizer_exists"])
    print("default_model_id:", h["default_model_id"])
    print()
    ok = h["tokenizer_exists"]
    for m in h["models"]:
        flag = "OK " if m["loadable"] else "MISS"
        print(f"[{flag}] {m['id']}: {m['path']}")
        if m["id"] == h["default_model_id"] and not m["loadable"]:
            ok = False
    print()
    if ok:
        print("READY: default model path + tokenizer look loadable")
        return 0
    print("NOT READY: fix paths in serve/configs/models_registry.yaml")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
