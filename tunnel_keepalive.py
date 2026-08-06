#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Стабильный доступ к переводчику.

Две проблемы, ради которых написан этот скрипт:
  1. Бесплатный туннель localhost.run живёт минуты и рвётся -> нужен
     автоперезапуск, иначе доступ пропадает без предупреждения.
  2. GitHub Pages деплоит с задержкой (сейчас деплой висит >20 мин), поэтому
     адрес нельзя публиковать через файл рядом со страницей. Пишем в api.json
     и пушим: страница читает его напрямую с raw.githubusercontent, который
     отдаёт свежий коммит немедленно и с CORS *.

Коммитим ТОЛЬКО при реальной смене адреса: каждый push перезапускает сборку
Pages, а частые push-и отменяют друг друга и деплой не завершается никогда.
"""
import re
import os
import subprocess
import sys
import time
import json
import urllib.request

# Пути и порт не прошиваем: скрипт лежит в самом репозитории сайта,
# порт берём из ING_API_PORT (как во всех .bat), иначе 8080 из .env.example.
SITE = os.path.dirname(os.path.abspath(__file__))
API_PORT = int(os.environ.get('ING_API_PORT', '8080'))
URL_RE = re.compile(rb'https://[a-z0-9-]+\.(?:lhr\.life|serveousercontent\.com)')
SSH = [
    'ssh', '-o', 'StrictHostKeyChecking=no',
    '-o', 'ServerAliveInterval=20', '-o', 'ServerAliveCountMax=3',
    '-o', 'ExitOnForwardFailure=yes',
    '-R', '80:127.0.0.1:%d' % API_PORT, 'nokey@localhost.run',
]


def log(msg):
    print('%s  %s' % (time.strftime('%H:%M:%S'), msg), flush=True)


def api_alive():
    try:
        with urllib.request.urlopen(
                'http://127.0.0.1:%d/health' % API_PORT, timeout=10) as r:
            return json.loads(r.read().decode()).get('ok') is True
    except Exception:                                    # noqa: BLE001
        return False


def tunnel_alive(addr):
    try:
        req = urllib.request.Request(addr + '/health')
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status == 200
    except Exception:                                    # noqa: BLE001
        return False


def publish(addr):
    """Записать адрес в api.json и запушить (только при смене)."""
    path = os.path.join(SITE, 'api.json')
    try:
        cur = json.load(open(path, encoding='utf-8')).get('api')
    except Exception:                                    # noqa: BLE001
        cur = None
    if cur == addr:
        return False

    json.dump({'api': addr,
               'updated': time.strftime('%Y-%m-%d %H:%M'),
               'note': 'Адрес обновляется автоматически при смене туннеля.'},
              open(path, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)

    env = dict(os.environ, LC_ALL='C.UTF-8')
    subprocess.run(['git', 'add', 'api.json'], cwd=SITE, env=env,
                   capture_output=True)
    subprocess.run(['git', 'commit', '-q', '-m', 'адрес сервера: ' + addr],
                   cwd=SITE, env=env, capture_output=True)
    p = subprocess.run(['git', 'push', '-q', 'origin', 'main'],
                       cwd=SITE, env=env, capture_output=True)
    log('опубликован %s (push rc=%d)' % (addr, p.returncode))
    return True


def main():
    if not api_alive():
        log('ОШИБКА: API на порту %d не отвечает' % API_PORT)
        sys.exit(1)

    while True:
        log('поднимаю туннель...')
        proc = subprocess.Popen(SSH, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        addr = None
        deadline = time.time() + 60
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            m = URL_RE.search(line)
            if m:
                cand = m.group(0).decode()
                if 'admin.' not in cand:
                    addr = cand
                    break

        if not addr:
            log('адрес не получен, перезапуск через 10 с')
            proc.kill()
            time.sleep(10)
            continue

        log('туннель: %s' % addr)
        publish(addr)

        # держим, пока жив; проверяем раз в 30 с
        while proc.poll() is None:
            time.sleep(30)
            if not tunnel_alive(addr):
                log('туннель перестал отвечать — перезапуск')
                proc.kill()
                break
        else:
            log('ssh завершился (rc=%s) — перезапуск' % proc.returncode)
        time.sleep(3)


if __name__ == '__main__':
    main()
