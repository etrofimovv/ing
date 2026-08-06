@echo off
chcp 65001 > nul
title Открыть доступ к переводчику из интернета

cd /d "%~dp0"

echo ====================================================================
echo  ДОСТУП К ПЕРЕВОДЧИКУ ИЗ ИНТЕРНЕТА
echo ====================================================================
echo.
echo Программа откроет доступ к вашему переводчику и сама пропишет
echo адрес на сайте. Ссылка для коллег всегда одна и та же:
echo.
echo      https://etrofimovv.github.io/ing/
echo.
echo Бесплатный туннель время от времени обрывается. Программа
echo поднимает его заново сама и публикует новый адрес — просто
echo не закрывайте это окно.
echo.
echo Перед запуском должен работать ЗАПУСТИТЬ_СЕРВЕР_API.bat
echo.
echo --------------------------------------------------------------------
echo.

rem ищем Python
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo !!! Python не найден. Сначала выполните УСТАНОВКА.bat
  echo.
  pause
  exit /b 1
)

rem tunnel_keepalive: сам перезапускает оборвавшийся туннель и коммитит
rem адрес только при реальной смене (частые push-и срывают сборку Pages).
%PY% tunnel_keepalive.py

echo.
echo Туннель закрыт. Ссылка больше не работает.
pause
