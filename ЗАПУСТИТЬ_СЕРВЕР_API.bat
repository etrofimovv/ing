@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem ============================================================
rem  СЕРВЕР ПЕРЕВОДА (API)
rem  Запускать на машине С ВИДЕОКАРТОЙ (например, с RTX 3090).
rem  Другие ПК в сети смогут переводить через неё.
rem
rem  ВАЖНО: в файле .env на ЭТОЙ машине должно быть
rem      ING_HOST=0.0.0.0
rem  иначе другие компьютеры не подключатся.
rem ============================================================

cd /d "%~dp0"

echo.
echo ============================================
echo   СЕРВЕР ПЕРЕВОДА (API)
echo ============================================
echo.

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [ОШИБКА] Нет окружения .venv
  echo Сначала запустите УСТАНОВКА.bat
  pause
  exit /b 1
)
set "VPY=%~dp0.venv\Scripts\python.exe"

rem --- показать IP машины для настройки клиентов ---
echo Адреса этой машины в локальной сети:
for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /c:"IPv4"') do (
  for /f "tokens=* delims= " %%B in ("%%A") do echo    http://%%B:8080
)
echo.
echo Впишите один из этих адресов в файл .env на других ПК:
echo    ING_MODE=remote
echo    ING_API_URL=http://^<адрес выше^>
echo.
echo Загружаю модель. Первый запуск: 1-5 минут.
echo НЕ ЗАКРЫВАЙТЕ это окно.
echo.

cd /d "%~dp0serve"
"%VPY%" -u app\api.py
set "EC=%ERRORLEVEL%"
echo.
echo [сервер остановлен, код %EC%]
pause
endlocal & exit /b %EC%
