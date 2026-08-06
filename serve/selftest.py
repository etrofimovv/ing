#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Самопроверка установки: грузит модель и переводит контрольные фразы.
Запускается автоматически из УСТАНОВКА.bat, можно вызвать вручную:

    .venv\\Scripts\\python.exe serve\\selftest.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

SERVE_DIR = Path(__file__).resolve().parent
if str(SERVE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVE_DIR))

# контрольные пары: (вход, ожидаемый фрагмент, что проверяем)
CHECKS = [
    ("Здравствуйте!", "Марша", "базовая лексика"),
    ("Это большой дом.", "цӏа", "класс Д + связка"),
    ("У него большой камень.", "кхера", "класс Б + связка"),
]


def main() -> int:
    try:
        from app.engine import DIR_RU2INH, get_engine
    except Exception as e:
        print("[ОШИБКА] Не удалось загрузить движок: %s: %s" % (type(e).__name__, e))
        print("Проверьте, что библиотеки установлены (УСТАНОВКА.bat).")
        return 1

    print("Загружаю модель. Первый раз это 1-5 минут...", flush=True)
    t0 = time.time()
    try:
        eng = get_engine()
        health = eng.health()
    except Exception as e:
        print("[ОШИБКА] Движок не стартовал: %s: %s" % (type(e).__name__, e))
        return 1

    models = eng.list_models()
    if not models:
        print("[ОШИБКА] В реестре нет моделей (serve/configs/models_registry.yaml)")
        return 1

    for m in models:
        if not m["exists"]:
            print("[ОШИБКА] Не найдена папка модели: %s" % m["path"])
            return 1
        if not m["loadable"]:
            print("[ОШИБКА] Модель не загружается: %s" % m["path"])
            return 1
        print("модель: %s — OK" % m["label"])

    ok = 0
    for text, expect, what in CHECKS:
        try:
            r = eng.translate(text=text, direction=DIR_RU2INH)
        except Exception as e:
            print("[ОШИБКА] Перевод упал на «%s»: %s: %s" % (text, type(e).__name__, e))
            return 1
        hit = expect.lower() in (r.translation or "").lower()
        ok += 1 if hit else 0
        print("  %s  %-28s -> %s   [%s, %.1f c]"
              % ("OK " if hit else "?? ", text, r.translation, what, r.latency_ms / 1000.0))

    dev = health.get("device", "?")
    print("\nустройство: %s | загрузка+тест: %.0f c" % (dev, time.time() - t0))

    if ok == 0:
        print("\n[ОШИБКА] Ни одна контрольная фраза не переведена правильно.")
        print("Вероятно, повреждены файлы модели — распакуйте архив заново.")
        return 1

    if ok < len(CHECKS):
        print("\nВНИМАНИЕ: совпало %d из %d контрольных фраз." % (ok, len(CHECKS)))
        print("Это допустимо: модель не идеальна, особенно в грамматическом классе.")
    else:
        print("\nВсе контрольные фразы переведены ожидаемо.")

    if dev == "cpu":
        print("\nРаботает на процессоре: 3-60 с на предложение.")
        print("Для скорости нужна видеокарта NVIDIA (RTX 3090 -> ~0.5 с).")

    print("\nСАМОПРОВЕРКА ПРОЙДЕНА")
    return 0


if __name__ == "__main__":
    sys.exit(main())
