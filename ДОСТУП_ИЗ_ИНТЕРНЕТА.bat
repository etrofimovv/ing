@echo off
chcp 65001 > nul
title Публичный доступ к переводчику (туннель в интернет)

cd /d "%~dp0"

echo ====================================================================
echo  ДОСТУП К ПЕРЕВОДЧИКУ ИЗ ИНТЕРНЕТА
echo ====================================================================
echo.
echo Эта программа делает ваш переводчик доступным по ссылке
echo из любой точки интернета - для коллег, с телефона, откуда угодно.
echo.
echo ВАЖНО: сначала должен быть запущен ЗАПУСТИТЬ_СЕРВЕР_API.bat
echo.
echo --------------------------------------------------------------------

rem порт API берём из .env, если он там указан
set "APIPORT=8080"
if exist ".env" (
  for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
    if /i "%%a"=="ING_API_PORT" if not "%%b"=="" set "APIPORT=%%b"
  )
)
set "APIPORT=%APIPORT: =%"

echo Проверяю, запущен ли сервер перевода на порту %APIPORT% ...
curl -s -m 5 -o nul "http://127.0.0.1:%APIPORT%/health"
if errorlevel 1 (
  echo.
  echo !!! Сервер перевода не отвечает на порту %APIPORT%.
  echo.
  echo Сначала запустите ЗАПУСТИТЬ_СЕРВЕР_API.bat и дождитесь,
  echo пока он напишет, что готов. Потом запустите этот файл снова.
  echo.
  pause
  exit /b 1
)
echo Сервер найден.
echo.

echo Создаю публичный адрес. Подождите 10-20 секунд...
echo.
echo --------------------------------------------------------------------
echo  Ниже появится строка вида:
echo     https://XXXXXX.lhr.life tunneled with tls termination
echo.
echo  Это и есть ваш адрес. Ссылку для коллег составьте так:
echo.
echo     https://etrofimovv.github.io/ing/?api=https://XXXXXX.lhr.life
echo.
echo  Коллеге достаточно открыть её - адрес подставится сам.
echo --------------------------------------------------------------------
echo.
echo  НЕ ЗАКРЫВАЙТЕ это окно: закроете - ссылка перестанет работать.
echo.

ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 80:127.0.0.1:%APIPORT% nokey@localhost.run

echo.
echo Туннель закрыт. Ссылка больше не работает.
pause
