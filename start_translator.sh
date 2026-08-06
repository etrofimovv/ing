#!/usr/bin/env bash
# ============================================================
#  ПЕРЕВОДЧИК RU -> ИНГУШСКИЙ — локальный запуск (Linux / macOS)
#
#    chmod +x start_translator.sh && ./start_translator.sh
#
#  Первый запуск ставит зависимости (нужен интернет),
#  дальше работает полностью офлайн.
#  Браузер: http://127.0.0.1:7860
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo
echo "============================================"
echo "  ПЕРЕВОДЧИК RU - ИНГУШСКИЙ (локально)"
echo "============================================"
echo

# --- Python ---
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "[ОШИБКА] Python 3 не найден. Установите Python 3.10+."
  exit 1
fi
echo "Python: $($PY --version)"

# --- venv рядом с пакетом (не трогаем системный python) ---
VENV="$ROOT/.venv"
if [ ! -d "$VENV" ]; then
  echo "Создаю окружение .venv ..."
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# --- зависимости ---
if ! python -c "import torch, transformers, peft, fastapi, uvicorn" 2>/dev/null; then
  echo
  echo "Первый запуск: устанавливаю библиотеки (5-10 мин, нужен интернет)."
  echo
  python -m pip install --upgrade pip
  python -m pip install -r "$ROOT/serve/requirements.txt"
else
  echo "Библиотеки: OK"
fi

# --- модели ---
if [ ! -f "$ROOT/models/v10-v6base-fixed/config.json" ]; then
  echo
  echo "[ОШИБКА] Не найдена базовая модель: $ROOT/models/v10-v6base-fixed/"
  echo "Папка models должна быть скопирована целиком (около 13 ГБ)."
  exit 1
fi
echo "Модели: OK"

echo
echo "Загружаю модель. Первый запуск: 2-5 минут."
echo "  Адрес: http://127.0.0.1:7860"
echo "  Остановить: Ctrl+C"
echo

mkdir -p "$ROOT/serve/logs"
cd "$ROOT/serve"
exec python -u app/ui_simple.py
