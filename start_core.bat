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
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
)
echo  ГОТОВО: Порты очищены.

:: -- 4. Launch servers --
echo [4/4] Запускаем серверы...
echo.

start "Backend :8000" /d "%BACKEND%" cmd /k "title Backend :8000 && chcp 65001 > nul && venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000 --host 0.0.0.0"
timeout /t 3 /nobreak > nul

start "Frontend :5173" /d "%FRONTEND%" cmd /k "title Frontend :5173 && chcp 65001 > nul && npm run dev"
timeout /t 5 /nobreak > nul

:: -- 5. Open browser --
echo Открываем браузер...
start "" http://localhost:5173

echo.
echo ============================================
echo   Бэкенд    http://localhost:8000
echo   Фронтенд  http://localhost:5173
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
