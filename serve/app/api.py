#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI обёртка над engine.py

  uvicorn app.api:app --host 127.0.0.1 --port 8080
  (запускать из каталога serve/)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

SERVE_DIR = Path(__file__).resolve().parent.parent
if str(SERVE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVE_DIR))

from app.engine import DIR_INH2RU, DIR_RU2INH, get_engine, load_yaml  # noqa: E402

app = FastAPI(title="ING NLLB Translator", version="0.1.0")

# CORS: страница на GitHub Pages обращается к этому API из браузера.
# Без этого браузер блокирует запрос (cross-origin).
# Список разрешённых сайтов задаётся в .env: ING_CORS_ORIGINS
# По умолчанию — GitHub Pages автора и localhost.
_origins_raw = (os.environ.get("ING_CORS_ORIGINS") or "").strip()
if _origins_raw == "*":
    _cors_kwargs = {"allow_origins": ["*"]}
elif _origins_raw:
    _cors_kwargs = {"allow_origins": [o.strip() for o in _origins_raw.split(",") if o.strip()]}
else:
    _cors_kwargs = {
        "allow_origins": [
            "https://etrofimovv.github.io",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    }

app.add_middleware(
    CORSMiddleware,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    **_cors_kwargs,
)


class TranslateIn(BaseModel):
    text: str = Field(..., min_length=1)
    direction: str = Field(default=DIR_RU2INH, description="ru2inh | inh2ru")
    model_id: Optional[str] = None
    num_beams: Optional[int] = Field(default=None, ge=1, le=8)
    max_length: Optional[int] = Field(default=None, ge=8, le=512)


class TranslateOut(BaseModel):
    text: str
    translation: str
    direction: str
    model_id: str
    src_lang: str
    tgt_lang: str
    latency_ms: float
    device: str


class BatchIn(BaseModel):
    texts: List[str]
    direction: str = DIR_RU2INH
    model_id: Optional[str] = None
    num_beams: Optional[int] = None
    max_length: Optional[int] = None


def _check_token(authorization: Optional[str]) -> None:
    cfg = load_yaml(SERVE_DIR / "configs" / "serve.yaml")
    token = (cfg.get("api_token") or os.environ.get("ING_API_TOKEN") or "").strip()
    if not token:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    got = authorization.split(" ", 1)[1].strip()
    if got != token:
        raise HTTPException(status_code=403, detail="invalid token")


@app.get("/health")
def health():
    eng = get_engine()
    return eng.health()


@app.get("/v1/models")
def models(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    eng = get_engine()
    return {"models": eng.list_models(), "loaded": eng.state.loaded_model_id}


@app.post("/v1/translate", response_model=TranslateOut)
def translate(body: TranslateIn, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    eng = get_engine()
    try:
        r = eng.translate(
            text=body.text,
            direction=body.direction,
            model_id=body.model_id,
            num_beams=body.num_beams,
            max_length=body.max_length,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    return TranslateOut(**r.__dict__)


@app.post("/v1/translate_batch")
def translate_batch(body: BatchIn, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    eng = get_engine()
    try:
        rs = eng.translate_batch(
            texts=body.texts,
            direction=body.direction,
            model_id=body.model_id,
            num_beams=body.num_beams,
            max_length=body.max_length,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    return {"items": [r.__dict__ for r in rs]}


@app.get("/")
def root():
    return {
        "service": "ing-nllb-translator",
        "endpoints": ["/health", "/v1/models", "/v1/translate", "/v1/translate_batch"],
        "directions": [DIR_RU2INH, DIR_INH2RU],
    }


def main():
    """Запуск API-сервера: python app/api.py (настройки берутся из .env)."""
    import uvicorn

    cfg = load_yaml(SERVE_DIR / "configs" / "serve.yaml")
    try:
        from app.envcfg import apply_to_serve_cfg
        cfg = apply_to_serve_cfg(cfg)
    except Exception:
        pass

    host = cfg.get("host") or "127.0.0.1"
    port = int(cfg.get("api_port") or 8080)

    # порт может быть занят другой программой — берём следующий свободный
    import socket

    probe = "127.0.0.1" if host == "0.0.0.0" else host
    for i in range(20):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.4)
        busy = s.connect_ex((probe, port + i)) == 0
        s.close()
        if not busy:
            if i:
                print("Порт %d занят — беру %d." % (port, port + i))
            port = port + i
            break

    print(f"API http://{host}:{port}")
    if host in ("127.0.0.1", "localhost"):
        print("ВНИМАНИЕ: доступ только с этой машины.")
        print("Чтобы дашборд с другого ПК мог подключиться, в .env задайте")
        print("  ING_HOST=0.0.0.0")
    else:
        print("Доступен по сети. Адрес для .env дашборда:")
        print(f"  ING_API_URL=http://<IP-этой-машины>:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
