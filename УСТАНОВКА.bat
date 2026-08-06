@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================
rem  УСТАНОВКА переводчика RU - ингушский
rem  Запустить ОДИН раз. Нужен интернет.
rem  Дальше работает офлайн: ЗАПУСТИТЬ_ПЕРЕВОДЧИК.bat
rem ============================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo   УСТАНОВКА ПЕРЕВОДЧИКА RU - ИНГУШСКИЙ
echo ============================================================
echo.
echo Что будет сделано:
echo   1. Проверка Python
echo   2. Создание изолированного окружения .venv
echo   3. Установка библиотек (2-6 ГБ, 5-15 минут)
echo   4. Проверка моделей
echo   5. Тестовый перевод
echo.
pause
echo.

rem ---------- 1. Python ----------
echo [1/5] Проверяю Python...
set "PY="
for %%V in (3.12 3.11 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  where python >nul 2>&1 && (
    for /f "tokens=2" %%A in ('python -V 2^>^&1') do set "PVER=%%A"
    echo     найден python !PVER!
    set "PY=python"
  )
)
if not defined PY (
  echo.
  echo [ОШИБКА] Python не найден.
  echo.
  echo Установите Python 3.11 или 3.12:
  echo   https://www.python.org/downloads/release/python-3129/
  echo.
  echo ВАЖНО: при установке отметьте галочку
  echo   [x] Add python.exe to PATH
  echo.
  echo Python 3.13 НЕ подходит - нужен 3.10, 3.11 или 3.12.
  echo.
  pause
  exit /b 1
)
echo     OK: %PY%

rem ---------- 2. venv ----------
echo.
echo [2/5] Создаю окружение .venv...
if exist "%~dp0.venv\Scripts\python.exe" (
  echo     уже существует, пропускаю
) else (
  %PY% -m venv "%~dp0.venv"
  if errorlevel 1 (
    echo [ОШИБКА] Не удалось создать .venv
    pause
    exit /b 1
  )
  echo     OK
)
set "VPY=%~dp0.venv\Scripts\python.exe"

rem ---------- 3. библиотеки ----------
echo.
echo [3/5] Устанавливаю библиотеки. Это долго (5-15 минут).
echo.
"%VPY%" -m pip install --upgrade pip --quiet

echo     - PyTorch (самая большая часть)...
"%VPY%" -c "import torch" >nul 2>&1
if errorlevel 1 (
  rem есть ли видеокарта NVIDIA?
  set "HASGPU="
  where nvidia-smi >nul 2>&1 && (
    nvidia-smi >nul 2>&1 && set "HASGPU=1"
  )
  if defined HASGPU (
    echo       обнаружена видеокарта NVIDIA - ставлю версию с CUDA ^(~2.5 ГБ^)
    "%VPY%" -m pip install torch --index-url https://download.pytorch.org/whl/cu124
    if errorlevel 1 (
      echo       CUDA-версия не встала, пробую CPU-версию...
      "%VPY%" -m pip install torch
    )
  ) else (
    echo       видеокарта NVIDIA не найдена - ставлю CPU-версию
    echo       ^(перевод будет медленным: 3-60 сек на предложение^)
    "%VPY%" -m pip install torch
  )
) else (
  echo       уже установлен
)

echo     - остальные библиотеки...
"%VPY%" -m pip install -r "%~dp0serve\requirements.txt"
if errorlevel 1 (
  echo.
  echo [ОШИБКА] Не удалось установить библиотеки.
  echo Проверьте интернет и запустите этот файл снова.
  pause
  exit /b 1
)
echo     OK

rem ---------- 4. модели ----------
echo.
echo [4/5] Проверяю модели...
if not exist "%~dp0models\v10-v6base-fixed\config.json" (
  echo.
  echo [ОШИБКА] Не найдена базовая модель:
  echo   %~dp0models\v10-v6base-fixed\
  echo.
  echo Папка models должна быть распакована целиком ^(~13 ГБ^).
  pause
  exit /b 1
)
if not exist "%~dp0models\v19-case-fixed\final\adapter_model.safetensors" (
  echo [ОШИБКА] Не найден адаптер models\v19-case-fixed\final\
  pause
  exit /b 1
)
if not exist "%~dp0tokenizers\nllb-200-rus-inh-v6\tokenizer.json" (
  echo [ОШИБКА] Не найден токенизатор tokenizers\nllb-200-rus-inh-v6\
  pause
  exit /b 1
)
echo     OK: база + адаптер F19 + токенизатор

rem ---------- 5. тест ----------
echo.
echo [5/5] Тестовый перевод. Первая загрузка: 1-5 минут.
echo.
"%VPY%" -u "%~dp0serve\selftest.py"
if errorlevel 1 (
  echo.
  echo [ОШИБКА] Тест не прошёл. Сообщите разработчику вывод выше.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo   УСТАНОВКА ЗАВЕРШЕНА
echo ============================================================
echo.
echo Запуск переводчика:  ЗАПУСТИТЬ_ПЕРЕВОДЧИК.bat
echo Настройки (если нужно): файл .env
echo.
pause
endlocal
