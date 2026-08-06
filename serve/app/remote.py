#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Клиент удалённого API (ING_MODE=remote в .env).

Этот ПК ничего не считает: отправляет текст на машину с видеокартой
и показывает ответ. Интерфейс тот же самый.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class RemoteResult:
    text: str
    translation: str
    direction: str
    model_id: str
    src_lang: str
    tgt_lang: str
    latency_ms: float
    device: str


class RemoteEngine:
    """Повторяет интерфейс TranslatorEngine, но ходит по HTTP."""

    def __init__(self, base_url: str, token: str = "", timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.token = (token or "").strip()
        self.timeout = timeout
        self.default_model_id = ""
        self._cache: Optional[List[dict]] = None

    # --- транспорт ---
    def _req(self, path: str, payload: Optional[dict] = None) -> Any:
        url = self.base_url + path
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method="POST" if data else "GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    # --- интерфейс движка ---
    def health(self) -> dict:
        try:
            h = self._req("/health")
            h["remote_url"] = self.base_url
            h["ok"] = True
            return h
        except Exception as e:
            return {
                "ok": False,
                "device": "удалённо",
                "loaded_model_id": None,
                "remote_url": self.base_url,
                "error": "%s: %s" % (type(e).__name__, e),
            }

    def list_models(self) -> List[dict]:
        if self._cache is not None:
            return self._cache
        try:
            data = self._req("/v1/models")
            models = data.get("models") or []
            for m in models:
                if m.get("is_default"):
                    self.default_model_id = m["id"]
            if not self.default_model_id and models:
                self.default_model_id = models[0]["id"]
            self._cache = models
            return models
        except Exception:
            return []

    def translate(self, text: str, direction: str, model_id: Optional[str] = None,
                  num_beams: Optional[int] = None,
                  max_length: Optional[int] = None) -> RemoteResult:
        payload: Dict[str, Any] = {"text": text, "direction": direction}
        if model_id:
            payload["model_id"] = model_id
        if num_beams:
            payload["num_beams"] = int(num_beams)
        if max_length:
            payload["max_length"] = int(max_length)
        try:
            r = self._req("/v1/translate", payload)
        except urllib.error.URLError as e:
            raise RuntimeError(
                "Нет связи с сервером перевода %s — %s.\n"
                "Проверьте: (1) на той машине запущен ЗАПУСТИТЬ_API.bat, "
                "(2) в её .env стоит ING_HOST=0.0.0.0, "
                "(3) адрес ING_API_URL в вашем .env верный, "
                "(4) брандмауэр пропускает порт." % (self.base_url, e)
            ) from None
        return RemoteResult(
            text=r.get("text", text),
            translation=r.get("translation", ""),
            direction=r.get("direction", direction),
            model_id=r.get("model_id", ""),
            src_lang=r.get("src_lang", ""),
            tgt_lang=r.get("tgt_lang", ""),
            latency_ms=float(r.get("latency_ms", 0.0)),
            device=r.get("device", "удалённо"),
        )
