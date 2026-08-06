#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Поднимает туннель в интернет и публикует его адрес на сайте.

Что делает:
  1. проверяет, что сервер перевода запущен;
  2. открывает туннель (localhost.run по SSH);
  3. записывает полученный адрес в api.json;
  4. отправляет api.json на GitHub;
  5. держит туннель открытым, а при обрыве — поднимает заново
     и снова обновляет адрес на сайте.

Ссылка для коллег при этом всегда одна и та же:
    https://etrofimovv.github.io/ing/
"""
import json
import io
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
API_JSON = os.path.join(HERE, "api.json")
SITE = "https://etrofimovv.github.io/ing/"

URL_RE = re.compile(rb"https://[a-z0-9-]+\.lhr\.life")


def log(msg):
    print(msg, flush=True)


def read_api_port():
    """Порт сервера перевода из .env, иначе 8080."""
    port = os.environ.get("ING_API_PORT") or ""
    env = os.path.join(HERE, ".env")
    if not port and os.path.exists(env):
        for line in io.open(env, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if line.startswith("ING_API_PORT"):
                _, _, val = line.partition("=")
                port = val.strip()
                break
    return port.strip() or "8080"


def server_alive(port):
    try:
        urllib.request.urlopen("http://127.0.0.1:%s/health" % port, timeout=5)
        return True
    except Exception:
        return False


def publish(address):
    """Записать адрес в api.json и отправить на GitHub."""
    data = {
        "api": address,
        "updated": time.strftime("%Y-%m-%d %H:%M"),
        "note": "Адрес обновляется автоматически при запуске туннеля.",
    }
    io.open(API_JSON, "w", encoding="utf-8").write(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    )

    env = dict(os.environ, LC_ALL="C.UTF-8", LANG="C.UTF-8")
    try:
        subprocess.run(["git", "add", "api.json"], cwd=HERE, env=env,
                       capture_output=True, timeout=60)
        r = subprocess.run(
            ["git", "-c", "i18n.commitEncoding=UTF-8", "commit",
             "-m", "адрес сервера: %s" % address],
            cwd=HERE, env=env, capture_output=True, timeout=60,
        )
        if r.returncode != 0 and b"nothing to commit" not in r.stdout:
            log("  git commit: " + r.stdout.decode("utf-8", "replace")[:200])
        r = subprocess.run(["git", "push", "origin", "main"], cwd=HERE, env=env,
                           capture_output=True, timeout=180)
        if r.returncode == 0:
            log("  адрес опубликован на сайте (обновится за 1-2 минуты)")
        else:
            log("  !!! не удалось отправить на GitHub:")
            log("      " + r.stderr.decode("utf-8", "replace")[:300])
    except Exception as e:
        log("  !!! ошибка публикации: %s" % e)


def run_tunnel(port):
    """Один цикл жизни туннеля. Возвращается, когда туннель закрылся."""
    cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3",
        "-o", "ExitOnForwardFailure=yes",
        "-R", "80:127.0.0.1:%s" % port, "nokey@localhost.run",
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    address = None
    for raw in iter(p.stdout.readline, b""):
        m = URL_RE.search(raw)
        if m and not address:
            address = m.group(0).decode()
            log("")
            log("  туннель открыт: %s" % address)
            publish(address)
            log("")
            log("  " + "=" * 60)
            log("  ССЫЛКА ДЛЯ КОЛЛЕГ (всегда одна и та же):")
            log("      %s" % SITE)
            log("  " + "=" * 60)
            log("")
            log("  Не закрывайте это окно.")
            log("")
    p.wait()
    return address


def main():
    port = read_api_port()
    log("Порт сервера перевода: %s" % port)

    if not server_alive(port):
        log("")
        log("!!! Сервер перевода не отвечает на порту %s." % port)
        log("    Сначала запустите ЗАПУСТИТЬ_СЕРВЕР_API.bat,")
        log("    дождитесь готовности и запустите этот файл снова.")
        return 1

    log("Сервер найден. Открываю туннель...")

    attempt = 0
    while True:
        attempt += 1
        try:
            run_tunnel(port)
        except KeyboardInterrupt:
            log("Остановлено.")
            return 0
        except Exception as e:
            log("  сбой туннеля: %s" % e)

        if not server_alive(port):
            log("Сервер перевода остановлен — выхожу.")
            return 0

        log("  туннель закрылся, поднимаю заново (попытка %d)..." % (attempt + 1))
        time.sleep(3)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
