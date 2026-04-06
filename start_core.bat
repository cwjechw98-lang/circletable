@echo off
chcp 65001 > nul 2>&1
title AI Round Table

echo ============================================
echo   Круглый стол ИИ  //  Быстрый запуск
echo ============================================
echo.

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "BACKEND_PORT=43117"
set "FRONTEND_PORT=43118"

:: -- 1. Python venv --
echo [1/4] Проверяем Python venv...
if not exist "%BACKEND%\venv\Scripts\python.exe" (
    echo  ИНФО: Создаём venv...
    python -m venv "%BACKEND%\venv"
    if errorlevel 1 (
        echo  ОШИБКА: Не удалось создать venv. Проверьте, установлен ли Python.
        goto :fail
    )
)

echo  ИНФО: Устанавливаем зависимости backend...
"%BACKEND%\venv\Scripts\pip.exe" install -r "%BACKEND%\requirements.txt" -q
if errorlevel 1 (
    echo  ОШИБКА: Установка зависимостей backend завершилась ошибкой.
    goto :fail
)
echo  ГОТОВО: Backend готов.

:: -- 2. Node modules --
echo [2/4] Проверяем Node-модули...
if not exist "%FRONTEND%\node_modules" (
    echo  ИНФО: Выполняем npm install...
    cd /d "%FRONTEND%"
    call npm install --silent
    if errorlevel 1 (
        echo  ОШИБКА: npm install завершился ошибкой. Проверьте, установлен ли Node.js.
        goto :fail
    )
    cd /d "%ROOT%"
)
echo  ГОТОВО: Frontend готов.

:: -- 3. Kill old instances --
echo [3/4] Очищаем старые запуски...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%BACKEND_PORT%" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%FRONTEND_PORT%" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
)
echo  ГОТОВО: Порты очищены.

:: -- 4. Launch servers --
echo [4/4] Запускаем серверы...
echo.

start "Backend :%BACKEND_PORT%" /d "%BACKEND%" cmd /k "title Backend :%BACKEND_PORT% && chcp 65001 > nul && venv\Scripts\python.exe -m uvicorn main:app --reload --port %BACKEND_PORT% --host 127.0.0.1"
timeout /t 3 /nobreak > nul

start "Frontend :%FRONTEND_PORT%" /d "%FRONTEND%" cmd /k "title Frontend :%FRONTEND_PORT% && chcp 65001 > nul && set \"VITE_API_PROXY_TARGET=http://127.0.0.1:%BACKEND_PORT%\" && npm run dev -- --host 127.0.0.1 --port %FRONTEND_PORT%"
timeout /t 5 /nobreak > nul

:: -- 5. Open browser --
echo Открываем браузер...
start "" http://127.0.0.1:%FRONTEND_PORT%

echo.
echo ============================================
echo   Бэкенд    http://127.0.0.1:%BACKEND_PORT%
echo   Фронтенд  http://127.0.0.1:%FRONTEND_PORT%
echo ============================================
echo.
echo  Оба сервера запущены в отдельных окнах.
echo  Нажмите любую клавишу, чтобы закрыть это окно запуска.
echo  Серверы продолжат работать.
echo.
pause > nul
exit /b 0

:fail
echo.
echo ============================================
echo  Запуск не удался. Подробности выше.
echo  Нажмите любую клавишу, чтобы закрыть окно.
echo ============================================
pause > nul
exit /b 1
