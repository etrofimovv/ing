#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Движок перевода NLLB (+ LoRA / merged).

- Не пишет в data/ и models/ (только читает пути из registry).
- Логика generate согласована с test_translation.sh / diagnose_gen.py.
- На torch<2.6 запрещён torch.load(.bin/.pt) — только safetensors.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

LANG_RU = "rus_Cyrl"
LANG_INH = "inh_Cyrl"
DIR_RU2INH = "ru2inh"
DIR_INH2RU = "inh2ru"


def _serve_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_project_root() -> Path:
    # serve/ -> 0_ING5
    return _serve_dir().parent


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass
class GenConfig:
    max_length: int = 128
    num_beams: int = 4
    no_repeat_ngram_size: int = 3
    repetition_penalty: float = 1.05
    max_source_length: int = 256


@dataclass
class ModelSpec:
    model_id: str
    label: str
    type: str  # lora | merged
    path: Path
    notes: str = ""
    tokenizer_path: Optional[Path] = None      # per-model (v5/v6E несовместимы)
    base_model_path: Optional[Path] = None     # per-model merged base (F9->v7, F12->v10)


@dataclass
class TranslateResult:
    text: str
    translation: str
    direction: str
    model_id: str
    src_lang: str
    tgt_lang: str
    latency_ms: float
    device: str


@dataclass
class EngineState:
    loaded_model_id: Optional[str] = None
    device: str = "cpu"
    dtype_name: str = "float32"
    load_error: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)


class TranslatorEngine:
    def __init__(
        self,
        project_root: Optional[Path] = None,
        serve_cfg_path: Optional[Path] = None,
        registry_path: Optional[Path] = None,
    ):
        self.serve_dir = _serve_dir()
        self.project_root = Path(project_root) if project_root else _default_project_root()

        cfg_path = Path(serve_cfg_path) if serve_cfg_path else self.serve_dir / "configs" / "serve.yaml"
        reg_path = Path(registry_path) if registry_path else self.serve_dir / "configs" / "models_registry.yaml"

        self.serve_cfg = load_yaml(cfg_path)
        # .env перекрывает YAML (путь к модели, устройство, порты)
        try:
            from app.envcfg import apply_to_serve_cfg
            self.serve_cfg = apply_to_serve_cfg(self.serve_cfg)
        except Exception:
            pass
        if self.serve_cfg.get("project_root"):
            self.project_root = Path(self.serve_cfg["project_root"]).expanduser().resolve()

        self.registry = load_yaml(reg_path)
        g = self.serve_cfg.get("generation") or {}
        self.gen = GenConfig(
            max_length=int(g.get("max_length", 128)),
            num_beams=int(g.get("num_beams", 4)),
            no_repeat_ngram_size=int(g.get("no_repeat_ngram_size", 3)),
            repetition_penalty=float(g.get("repetition_penalty", 1.05)),
            max_source_length=int(g.get("max_source_length", 256)),
        )
        self.default_model_id = self.serve_cfg.get("default_model_id") or "s2_h100_final"
        self.tokenizer_path = self._resolve(self.serve_cfg.get("tokenizer_path") or "tokenizers/nllb-200-rus-inh")
        self.base_model_name = self.serve_cfg.get("base_model_name") or "facebook/nllb-200-3.3B"
        self.dtype_pref = (self.serve_cfg.get("dtype") or "float16").lower()
        self.device_pref = (self.serve_cfg.get("device") or "auto").lower()

        self._lock = threading.Lock()
        self._model = None
        self._tokenizer = None
        self._bos_ru: Optional[int] = None
        self._bos_inh: Optional[int] = None
        self.state = EngineState()

    def _resolve(self, rel: str | Path) -> Path:
        p = Path(rel)
        if p.is_absolute():
            return p
        return (self.project_root / p).resolve()

    def list_models(self) -> List[dict]:
        out = []
        models = (self.registry.get("models") or {})
        for mid, meta in models.items():
            path = self._resolve(meta.get("path") or "")
            exists = path.is_dir()
            has_adapter = (path / "adapter_config.json").is_file() or (path / "adapter_model.safetensors").is_file()
            has_full = (path / "config.json").is_file() and (
                any(path.glob("model*.safetensors")) or (path / "pytorch_model.bin").is_file()
            )
            out.append(
                {
                    "id": mid,
                    "label": meta.get("label") or mid,
                    "type": meta.get("type") or "lora",
                    "path": str(path),
                    "exists": exists,
                    "loadable": exists and (has_adapter or has_full or (meta.get("type") == "merged" and has_full)),
                    "notes": meta.get("notes") or "",
                    "is_default": mid == self.default_model_id,
                }
            )
        return out

    def get_spec(self, model_id: str) -> ModelSpec:
        models = self.registry.get("models") or {}
        if model_id not in models:
            raise KeyError(f"Unknown model_id={model_id}. Known: {list(models)}")
        meta = models[model_id]
        return ModelSpec(
            model_id=model_id,
            label=meta.get("label") or model_id,
            type=(meta.get("type") or "lora").lower(),
            path=self._resolve(meta.get("path") or ""),
            notes=meta.get("notes") or "",
            tokenizer_path=(
                self._resolve(meta["tokenizer_path"]) if meta.get("tokenizer_path") else None
            ),
            base_model_path=(
                self._resolve(meta["base_model_path"]) if meta.get("base_model_path") else None
            ),
        )

    def _pick_device(self):
        import torch

        if self.device_pref == "cpu":
            return "cpu"
        if self.device_pref == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError("device=cuda but CUDA not available")
            return "cuda"
        return "cuda" if torch.cuda.is_available() else "cpu"

    def _pick_dtype(self, device: str):
        import torch

        if device == "cpu":
            return torch.float32, "float32"
        if self.dtype_pref in ("float16", "fp16", "half"):
            return torch.float16, "float16"
        if self.dtype_pref in ("bfloat16", "bf16"):
            return torch.bfloat16, "bfloat16"
        return torch.float32, "float32"

    def ensure_loaded(self, model_id: Optional[str] = None) -> str:
        mid = model_id or self.default_model_id
        with self._lock:
            if self._model is not None and self.state.loaded_model_id == mid:
                return mid
            self._load_unlocked(mid)
            return mid

    def _block_unsafe_torch_load(self):
        """On torch<2.6 block torch.load of .bin/.pt (CVE-2025-32434)."""
        import torch

        ver = tuple(int(x) for x in torch.__version__.split("+")[0].split(".")[:2])
        if ver >= (2, 6):
            return None  # no patch needed
        if getattr(torch.load, "_ing_cve_patched", False):
            return torch.load

        orig = torch.load

        def guarded_load(*args, **kwargs):
            path = args[0] if args else kwargs.get("f")
            p = str(path) if path is not None else ""
            # allow only non-weight aux if ever needed — by default block weight-like files
            lower = p.lower()
            if lower.endswith((".bin", ".pt", ".pth", ".ckpt")) and "safetensor" not in lower:
                raise ValueError(
                    "Blocked torch.load of non-safetensors file on torch<2.6 "
                    f"(CVE-2025-32434): {p}. "
                    "Serve loads only adapter_model.safetensors / model*.safetensors. "
                    "If you see this, UI may be stale or model dir has only .bin weights. "
                    "Use s2_h100_final and restart START_TRANSLATOR.bat."
                )
            return orig(*args, **kwargs)

        guarded_load._ing_cve_patched = True  # type: ignore[attr-defined]
        torch.load = guarded_load  # type: ignore[assignment]
        return orig

    def _adapter_safetensors_only_dir(self, adapter_dir: Path) -> Path:
        """
        Peft/transformers may try torch.load(training_args.bin) from full checkpoint dirs.
        Copy ONLY safe adapter files into a temp dir for loading.
        """
        src_st = adapter_dir / "adapter_model.safetensors"
        src_cfg = adapter_dir / "adapter_config.json"
        if not src_st.is_file():
            raise FileNotFoundError(
                f"adapter_model.safetensors not found in {adapter_dir}. "
                "Refuse to load .bin/.pt via torch.load on torch<2.6."
            )
        if not src_cfg.is_file():
            raise FileNotFoundError(f"adapter_config.json not found in {adapter_dir}")

        tmp = Path(tempfile.mkdtemp(prefix="ing_adapter_safe_"))
        shutil.copy2(src_st, tmp / "adapter_model.safetensors")
        shutil.copy2(src_cfg, tmp / "adapter_config.json")
        # optional: nothing else (no training_args.bin, optimizer.pt, tokenizer.bin)
        return tmp

    def _load_unlocked(self, model_id: str) -> None:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        # free previous
        if self._model is not None:
            del self._model
            self._model = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        spec = self.get_spec(model_id)
        if not spec.path.is_dir():
            raise FileNotFoundError(f"Model path not found: {spec.path}")

        # per-model tokenizer (v5/v6E несовместимы) > глобальный > tokenizer в папке модели
        if spec.tokenizer_path is not None:
            tok_dir = spec.tokenizer_path
        elif self.tokenizer_path.is_dir():
            tok_dir = self.tokenizer_path
        elif (spec.path / "tokenizer.json").is_file():
            tok_dir = spec.path
        else:
            raise FileNotFoundError(
                f"Tokenizer not found for {model_id}: checked per-model, {self.tokenizer_path}, {spec.path}"
            )

        device = self._pick_device()
        dtype, dtype_name = self._pick_dtype(device)

        # Patch torch.load BEFORE any HF/peft load on torch<2.6
        self._block_unsafe_torch_load()

        # peft 0.19.1 + torch 2.11: peft проверяет isinstance(w, torch.distributed.tensor.DTensor),
        # но подмодуль torch.distributed.tensor подгружается лениво -> AttributeError без импорта.
        try:
            import torch.distributed.tensor  # noqa: F401
        except Exception:
            pass

        # Stack: transformers 4.44.2 + safetensors only (боевой venv nllb-lora-env)
        tokenizer = AutoTokenizer.from_pretrained(str(tok_dir))
        bos_ru = tokenizer.convert_tokens_to_ids(LANG_RU)
        bos_inh = tokenizer.convert_tokens_to_ids(LANG_INH)
        if bos_ru is None or bos_inh is None or bos_ru < 0 or bos_inh < 0 or bos_inh == 3:
            raise RuntimeError(
                f"Bad BOS ids: rus_Cyrl={bos_ru}, inh_Cyrl={bos_inh}. Check patched tokenizer."
            )

        # per-model base (merged) > глобальный
        base_name = str(spec.base_model_path) if spec.base_model_path is not None else self.base_model_name

        # merge адаптера делаем в fp32, потом каст в bf16 (opus 5: избежать двойного округления)
        common = {
            "torch_dtype": torch.float32,
            "use_safetensors": True,
            # грузим шардами, не держим вторую копию весов в RAM:
            # без этого пик достигает ~26 ГБ и падает на машинах с 16 ГБ
            "low_cpu_mem_usage": True,
        }

        tmp_adapter = None
        try:
            if spec.type == "merged":
                if not any(spec.path.glob("*.safetensors")):
                    raise FileNotFoundError(
                        f"No *.safetensors in merged model {spec.path}"
                    )
                model = AutoModelForSeq2SeqLM.from_pretrained(str(spec.path), **common)
            else:
                from peft import PeftModel

                tmp_adapter = self._adapter_safetensors_only_dir(spec.path)
                base = AutoModelForSeq2SeqLM.from_pretrained(base_name, **common)
                model = PeftModel.from_pretrained(base, str(tmp_adapter))
                model = model.merge_and_unload()

            # fail-fast (opus 5): vocab токенизатора обязан совпадать с embedding модели.
            # v6E (27381) и v5 (285581) несовместимы — несовпадение = неверный токенизатор.
            emb_rows = model.get_input_embeddings().weight.shape[0]
            tok_len = len(tokenizer)
            if emb_rows != tok_len:
                raise RuntimeError(
                    f"Vocab mismatch for {model_id}: len(tokenizer)={tok_len} vs "
                    f"embed_tokens={emb_rows}. Токенизатор не соответствует модели "
                    f"(v5/v6E несовместимы). Проверь tokenizer_path в registry."
                )

            model = model.to(device=device, dtype=dtype)
            model.eval()
            model.config.forced_bos_token_id = bos_inh
            model.config.decoder_start_token_id = bos_inh

            self._tokenizer = tokenizer
            self._model = model
            self._bos_ru = bos_ru
            self._bos_inh = bos_inh
            self.state = EngineState(
                loaded_model_id=model_id,
                device=device,
                dtype_name=dtype_name,
                load_error=None,
                extras={
                    "path": str(spec.path),
                    "type": spec.type,
                    "label": spec.label,
                    "use_safetensors": True,
                    "torch": getattr(torch, "__version__", "?"),
                    "adapter_safe_dir": str(tmp_adapter) if tmp_adapter else "",
                },
            )
        finally:
            if tmp_adapter is not None:
                try:
                    shutil.rmtree(tmp_adapter, ignore_errors=True)
                except Exception:
                    pass

    def unload(self) -> None:
        import torch

        with self._lock:
            self._model = None
            self._tokenizer = None
            self.state.loaded_model_id = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def _direction_langs(self, direction: str):
        d = (direction or DIR_RU2INH).strip().lower()
        if d in (DIR_RU2INH, "ru-inh", "ru_inh", "rus2inh"):
            return DIR_RU2INH, LANG_RU, LANG_INH, self._bos_inh
        if d in (DIR_INH2RU, "inh-ru", "inh_ru", "inh2rus"):
            return DIR_INH2RU, LANG_INH, LANG_RU, self._bos_ru
        raise ValueError(f"direction must be {DIR_RU2INH}|{DIR_INH2RU}, got {direction!r}")

    def translate(
        self,
        text: str,
        direction: str = DIR_RU2INH,
        model_id: Optional[str] = None,
        num_beams: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> TranslateResult:
        text = (text or "").strip()
        if not text:
            raise ValueError("empty text")

        mid = self.ensure_loaded(model_id)
        direction, src_lang, tgt_lang, forced_bos = self._direction_langs(direction)
        if forced_bos is None:
            raise RuntimeError("model not loaded")

        beams = int(num_beams if num_beams is not None else self.gen.num_beams)
        max_len = int(max_length if max_length is not None else self.gen.max_length)

        import torch

        t0 = time.perf_counter()
        with self._lock:
            tokenizer = self._tokenizer
            model = self._model
            device = self.state.device

            # Same as edu19/diagnose_gen: src_lang + tgt_lang on tokenizer
            tokenizer.src_lang = src_lang
            if hasattr(tokenizer, "tgt_lang"):
                tokenizer.tgt_lang = tgt_lang

            # Keep config in sync with requested direction (bidirectional)
            model.config.forced_bos_token_id = forced_bos
            model.config.decoder_start_token_id = forced_bos
            if getattr(model, "generation_config", None) is not None:
                model.generation_config.forced_bos_token_id = forced_bos
                model.generation_config.decoder_start_token_id = forced_bos

            batch = tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=self.gen.max_source_length,
            )
            dev = next(model.parameters()).device
            batch = {k: v.to(dev) for k, v in batch.items()}

            with torch.inference_mode():
                outputs = model.generate(
                    **batch,
                    forced_bos_token_id=forced_bos,
                    max_length=max_len,
                    num_beams=beams,
                    no_repeat_ngram_size=self.gen.no_repeat_ngram_size,
                    repetition_penalty=self.gen.repetition_penalty,
                )
            translation = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

        latency = (time.perf_counter() - t0) * 1000.0
        return TranslateResult(
            text=text,
            translation=translation,
            direction=direction,
            model_id=mid,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
            latency_ms=round(latency, 1),
            device=self.state.device,
        )

    def translate_batch(
        self,
        texts: List[str],
        direction: str = DIR_RU2INH,
        model_id: Optional[str] = None,
        num_beams: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> List[TranslateResult]:
        # sequential safe path (UI/API single-user); batch tensor path can be added later
        return [
            self.translate(
                t,
                direction=direction,
                model_id=model_id,
                num_beams=num_beams,
                max_length=max_length,
            )
            for t in texts
            if (t or "").strip()
        ]

    def health(self) -> dict:
        models = self.list_models()
        return {
            "ok": True,
            "project_root": str(self.project_root),
            "tokenizer_path": str(self.tokenizer_path),
            "tokenizer_exists": self.tokenizer_path.is_dir(),
            "default_model_id": self.default_model_id,
            "loaded_model_id": self.state.loaded_model_id,
            "device": self.state.device,
            "dtype": self.state.dtype_name,
            "models": models,
        }


# singleton helper for UI/API
_ENGINE: Optional[TranslatorEngine] = None
_ENGINE_LOCK = threading.Lock()


def get_engine() -> TranslatorEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = TranslatorEngine()
        return _ENGINE
