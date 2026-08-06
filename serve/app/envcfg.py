#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Чтение .env и применение настроек поверх YAML-конфигов.

Файл .env лежит в корне пакета (рядом с папкой serve/).
Пустые значения игнорируются — работает то, что в YAML.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict


def _pkg_root() -> Path:
    # app/envcfg.py -> serve/ -> корень пакета
    return Path(__file__).resolve().parent.parent.parent


def load_env(path: Path | None = None) -> Dict[str, str]:
    """Читает .env в словарь и в os.environ (не перетирая уже заданное извне)."""
    env_path = Path(path) if path else _pkg_root() / ".env"
    data: Dict[str, str] = {}
    if not env_path.is_file():
        return data
    with open(env_path, "r", encoding="utf-8-sig") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if not k:
                continue
            data[k] = v
            if v and k not in os.environ:
                os.environ[k] = v
    return data


def get(key: str, default: str = "") -> str:
    v = os.environ.get(key, "")
    return v.strip() if v and v.strip() else default


def get_int(key: str, default: int) -> int:
    try:
        return int(get(key, str(default)))
    except ValueError:
        return default


def apply_to_serve_cfg(cfg: dict) -> dict:
    """Накладывает переменные .env на словарь serve.yaml."""
    load_env()

    root = get("ING_ROOT")
    if root:
        cfg["project_root"] = root

    device = get("ING_DEVICE")
    if device:
        cfg["device"] = device

    dtype = get("ING_DTYPE")
    if dtype:
        cfg["dtype"] = dtype

    host = get("ING_HOST")
    if host:
        cfg["host"] = host

    ui_port = get("ING_UI_PORT")
    if ui_port:
        cfg["ui_port"] = get_int("ING_UI_PORT", int(cfg.get("ui_port", 7860)))

    api_port = get("ING_API_PORT")
    if api_port:
        cfg["api_port"] = get_int("ING_API_PORT", int(cfg.get("api_port", 8080)))

    token = get("ING_API_TOKEN")
    if token:
        cfg["api_token"] = token

    gen = cfg.setdefault("generation", {})
    nb = get("ING_NUM_BEAMS")
    if nb:
        gen["num_beams"] = get_int("ING_NUM_BEAMS", int(gen.get("num_beams", 4)))
    ml = get("ING_MAX_LENGTH")
    if ml:
        gen["max_length"] = get_int("ING_MAX_LENGTH", int(gen.get("max_length", 128)))

    return cfg


def mode() -> str:
    """local | remote"""
    load_env()
    m = get("ING_MODE", "local").lower()
    return "remote" if m == "remote" else "local"


def api_url() -> str:
    load_env()
    return get("ING_API_URL").rstrip("/")
