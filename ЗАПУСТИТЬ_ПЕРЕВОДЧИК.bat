@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem ============================================================
rem  ПЕРЕВОДЧИК RU -> ИНГУШСКИЙ
rem  Двойной клик. Браузер откроется сам.
rem  Если это первый раз — сначала запустите УСТАНОВКА.bat
rem ============================================================

cd /d "%~dp0"

echo.
echo ============================================
echo   ПЕРЕВОДЧИК RU - ИНГУШСКИЙ
echo ============================================
echo.

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [ОШИБКА] Программа не установлена.
  echo.
  echo Запустите сначала:  УСТАНОВКА.bat
  echo.
  pause
  exit /b 1
)
set "VPY=%~dp0.venv\Scripts\python.exe"

rem --- читаем порт из .env (по умолчанию 7860) ---
set "UIPORT=7860"
if exist "%~dp0.env" (
  for /f "usebackq tokens=1,2 delims==" %%A in ("%~dp0.env") do (
    if /i "%%A"=="ING_UI_PORT" if not "%%B"=="" set "UIPORT=%%B"
  )
)

echo Загружаю модель. Первый запуск: 1-5 минут.
echo Браузер откроется автоматически, когда всё будет готово.
echo.
echo   НЕ ЗАКРЫВАЙТЕ это окно во время работы.
echo   Остановить: закрыть окно или Ctrl+C
echo.

cd /d "%~dp0serve"
"%VPY%" -u app\ui_simple.py
set "EC=%ERRORLEVEL%"

echo.
if not "%EC%"=="0" (
  echo [код выхода %EC%]
  echo Если перевод работал — всё в порядке.
)
pause
endlocal & exit /b %EC%
