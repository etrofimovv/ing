#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Простой UI переводчика без Gradio (FastAPI + HTML).
Обходит конфликт gradio/jinja/starlette в shared venv.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SERVE_DIR = Path(__file__).resolve().parent.parent
if str(SERVE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVE_DIR))

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from app.engine import DIR_INH2RU, DIR_RU2INH, get_engine as _get_local_engine, load_yaml

_REMOTE = None


def get_engine():
    """Локальный движок или клиент удалённого API — по ING_MODE в .env."""
    global _REMOTE
    try:
        from app.envcfg import api_url, get as env_get, mode
        if mode() == "remote":
            url = api_url()
            if not url:
                raise RuntimeError(
                    "ING_MODE=remote, но ING_API_URL пуст. "
                    "Укажите адрес машины с моделью в файле .env, например "
                    "ING_API_URL=http://192.168.1.50:8080"
                )
            if _REMOTE is None:
                from app.remote import RemoteEngine
                _REMOTE = RemoteEngine(url, env_get("ING_API_TOKEN"))
                _REMOTE.list_models()
            return _REMOTE
    except RuntimeError:
        raise
    except Exception:
        pass
    return _get_local_engine()


app = FastAPI(title="ING Translator", version="0.2.0")

PAGE = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>ING Translator</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; background:#f6f7fb; color:#111; }}
    .wrap {{ max-width: 980px; margin: 0 auto; }}
    .card {{ background:#fff; border:1px solid #e5e7eb; border-radius:12px; padding:18px; margin-bottom:16px; }}
    h1 {{ margin:0 0 8px; font-size:22px; }}
    .muted {{ color:#6b7280; font-size:13px; }}
    textarea, select, input[type=number] {{ width:100%; box-sizing:border-box; padding:10px; border:1px solid #d1d5db; border-radius:8px; font-size:15px; }}
    textarea {{ min-height: 140px; resize: vertical; }}
    label {{ display:block; font-weight:600; margin:10px 0 6px; }}
    .row {{ display:grid; grid-template-columns: 1fr 1fr 120px 120px; gap:12px; }}
    button {{ background:#2563eb; color:#fff; border:0; border-radius:8px; padding:12px 18px; font-size:15px; cursor:pointer; }}
    button:hover {{ background:#1d4ed8; }}
    .out {{ white-space: pre-wrap; background:#f9fafb; border:1px solid #e5e7eb; border-radius:8px; padding:12px; min-height:120px; }}
    .err {{ color:#b91c1c; white-space: pre-wrap; }}
    .ok {{ color:#065f46; }}
    @media (max-width: 800px) {{ .row {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>Переводчик RU ↔ ING (NLLB)</h1>
    <div class="muted">{mode_line}</div>
  </div>

  <form class="card" method="post" action="/">
    <label>Текст</label>
    <textarea name="text" placeholder="Введите текст…">{text_value}</textarea>

    <div class="row">
      <div>
        <label>Направление</label>
        <select name="direction">
          <option value="ru2inh" {sel_ru}>RU → INH</option>
          <option value="inh2ru" disabled title="Не обучено: F9/F12/F13 тренированы только ru2inh (BLEU 1.28)">INH → RU (не обучено)</option>
        </select>
      </div>
      <div>
        <label>Модель</label>
        <select name="model_id">
          {model_options}
        </select>
      </div>
      <div>
        <label>beams</label>
        <input type="number" name="num_beams" min="1" max="8" value="{beams}"/>
      </div>
      <div>
        <label>max_len</label>
        <input type="number" name="max_length" min="32" max="256" step="8" value="{max_len}"/>
      </div>
    </div>

    <div style="margin-top:14px">
      <button type="submit">Перевести</button>
    </div>
  </form>

  <div class="card">
    <label>Перевод</label>
    <div class="out">{translation}</div>
    <div class="{status_class}" style="margin-top:10px">{status}</div>
  </div>

  <div class="card muted">
    <div>Health: loaded={loaded} device={device}</div>
    <div>API: <code>/health</code> · <code>/v1/translate</code></div>
  </div>
</div>
</body>
</html>
"""


def _options(models, selected: str) -> str:
    parts = []
    for m in models:
        mid = m["id"]
        mark = "✓" if m.get("loadable") else "✗"
        label = f'{mid} | {m.get("label", mid)} [{mark}]'
        sel = "selected" if mid == selected else ""
        parts.append(f'<option value="{mid}" {sel}>{label}</option>')
    return "\n".join(parts)


def _mode_line() -> str:
    try:
        from app.envcfg import api_url, mode
        if mode() == "remote":
            return "Режим: удалённый · перевод считает %s" % (api_url() or "?")
    except Exception:
        pass
    return "Локальный переводчик · модель F19 · данные никуда не отправляются"


def _page(text="", direction="ru2inh", model_id=None, beams=4, max_len=128,
          translation="", status="", status_class="muted"):
    eng = get_engine()
    models = eng.list_models()
    if not model_id:
        model_id = eng.default_model_id
    h = eng.health()
    return PAGE.format(
        mode_line=_mode_line(),
        text_value=(text or "").replace("<", "&lt;"),
        sel_ru="selected" if direction == DIR_RU2INH else "",
        sel_inh="selected" if direction == DIR_INH2RU else "",
        model_options=_options(models, model_id),
        beams=beams,
        max_len=max_len,
        translation=(translation or "").replace("<", "&lt;") or "—",
        status=status or "",
        status_class=status_class,
        loaded=h.get("loaded_model_id"),
        device=h.get("device"),
    )


@app.get("/", response_class=HTMLResponse)
def index():
    eng = get_engine()
    g = (load_yaml(SERVE_DIR / "configs" / "serve.yaml").get("generation") or {})
    return _page(
        beams=int(g.get("num_beams", 4)),
        max_len=int(g.get("max_length", 128)),
        status="Готов. Введите текст и нажмите «Перевести».",
        status_class="ok",
    )


@app.post("/", response_class=HTMLResponse)
async def translate_form(
    text: str = Form(""),
    direction: str = Form(DIR_RU2INH),
    model_id: str = Form(""),
    num_beams: int = Form(4),
    max_length: int = Form(128),
):
    eng = get_engine()
    if direction == DIR_INH2RU:
        return _page(
            text=text,
            direction=DIR_RU2INH,
            model_id=model_id or None,
            beams=num_beams,
            max_len=max_length,
            translation="",
            status="Направление INH → RU отключено: модели F9/F12/F13 обучены только ru2inh "
                   "(в data/gold нет колонки direction), BLEU обратного направления 1.28.",
            status_class="muted",
        )
    try:
        r = eng.translate(
            text=text,
            direction=direction,
            model_id=model_id or None,
            num_beams=num_beams,
            max_length=max_length,
        )
        status = (
            f"OK · model={r.model_id} · {r.src_lang}→{r.tgt_lang} · "
            f"{r.latency_ms} ms · device={r.device}"
        )
        return _page(
            text=text,
            direction=direction,
            model_id=r.model_id,
            beams=num_beams,
            max_len=max_length,
            translation=r.translation,
            status=status,
            status_class="ok",
        )
    except Exception as e:
        return _page(
            text=text,
            direction=direction,
            model_id=model_id,
            beams=num_beams,
            max_len=max_length,
            translation="",
            status=f"ERROR: {type(e).__name__}: {e}",
            status_class="err",
        )


# Reuse API routes from api.py by including them lightly
@app.get("/health")
def health():
    return get_engine().health()


@app.get("/v1/models")
def models():
    eng = get_engine()
    return {"models": eng.list_models(), "loaded": eng.state.loaded_model_id}


def _free_port(host: str, port: int, tries: int = 20) -> int:
    """Если порт занят (другой программой) — берём следующий свободный."""
    import socket

    probe_host = "127.0.0.1" if host == "0.0.0.0" else host
    for i in range(tries):
        p = port + i
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.4)
        busy = s.connect_ex((probe_host, p)) == 0
        s.close()
        if not busy:
            if i:
                print("Порт %d занят другой программой — беру %d." % (port, p))
            return p
    return port


def _open_browser_later(url: str, delay: float = 20.0) -> None:
    import threading
    import webbrowser

    def go():
        import time

        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=go, daemon=True).start()


def main():
    cfg = load_yaml(SERVE_DIR / "configs" / "serve.yaml")
    # .env перекрывает YAML (host/порт задаются там)
    try:
        from app.envcfg import apply_to_serve_cfg
        cfg = apply_to_serve_cfg(cfg)
    except Exception:
        pass
    host = cfg.get("host") or "127.0.0.1"
    port = _free_port(host, int(cfg.get("ui_port") or 7860))
    url = "http://%s:%d" % ("127.0.0.1" if host == "0.0.0.0" else host, port)
    print("=" * 52)
    print("  ПЕРЕВОДЧИК ГОТОВИТСЯ. Адрес: %s" % url)
    print("  Браузер откроется сам. Не закрывайте это окно.")
    print("=" * 52)
    if os.environ.get("ING_NO_BROWSER", "").strip() not in ("1", "true", "yes"):
        _open_browser_later(url)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
