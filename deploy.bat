@echo off
chcp 65001 > nul
title Публикация сайта-переводчика на GitHub Pages

rem кириллица в сообщениях коммитов должна быть в UTF-8
set "LC_ALL=C.UTF-8"
set "LANG=C.UTF-8"

echo ====================================================================
echo  Публикация сайта переводчика RU - ингушский
echo ====================================================================
echo.
echo Отправляю файлы в репозиторий:
echo https://github.com/etrofimovv/ing
echo.
echo Если появится окно входа - выберите "Sign in with your browser"
echo и подтвердите доступ для аккаунта etrofimovv.
echo.
echo --------------------------------------------------------------------

cd /d "%~dp0"

git -c i18n.commitEncoding=UTF-8 -c core.quotepath=false status --short
echo.

git diff --quiet --exit-code HEAD 2>nul
if errorlevel 1 goto :commit
git ls-files --others --exclude-standard | findstr /r "." >nul 2>&1
if not errorlevel 1 goto :commit

echo Изменений нет - отправляю то, что уже закоммичено.
goto :push

:commit
set "MSG="
set /p MSG="Опишите изменения (Enter = 'обновление сайта'): "
if "%MSG%"=="" set "MSG=обновление сайта"
git add -A
git -c i18n.commitEncoding=UTF-8 commit -m "%MSG%"
echo.

:push
git push -u origin main
if errorlevel 1 (
  echo.
  echo !!! Не удалось отправить. Проверьте интернет и вход в GitHub.
  echo.
  pause
  exit /b 1
)

echo --------------------------------------------------------------------
echo.
echo Готово. Файлы загружены на GitHub.
echo.
echo Сайт обновится через 1-2 минуты:
echo    https://etrofimovv.github.io/ing/
echo.
echo Напоминание: сайт - это только интерфейс.
echo Чтобы перевод работал, на компьютере с моделью должен быть
echo запущен ЗАПУСТИТЬ_СЕРВЕР_API.bat
echo.
echo ====================================================================
pause
