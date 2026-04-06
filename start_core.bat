@echo off
chcp 65001 > nul 2>&1
title AI Round Table

echo ============================================
echo   AI Round Table  //  Quick Launcher
echo ============================================
echo.

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

:: -- 1. Python venv --
echo [1/4] Checking Python venv...
if not exist "%BACKEND%\venv\Scripts\python.exe" (
    echo  INFO: Creating venv...
    python -m venv "%BACKEND%\venv"
    if errorlevel 1 (
        echo  ERROR: Could not create venv. Is Python installed?
        goto :fail
    )
)

echo  INFO: Installing backend deps...
"%BACKEND%\venv\Scripts\pip.exe" install -r "%BACKEND%\requirements.txt" -q
if errorlevel 1 (
    echo  ERROR: pip install failed.
    goto :fail
)
echo  OK: Backend ready.

:: -- 2. Node modules --
echo [2/4] Checking Node modules...
if not exist "%FRONTEND%\node_modules" (
    echo  INFO: Running npm install...
    cd /d "%FRONTEND%"
    call npm install --silent
    if errorlevel 1 (
        echo  ERROR: npm install failed. Is Node.js installed?
        goto :fail
    )
    cd /d "%ROOT%"
)
echo  OK: Frontend ready.

:: -- 3. Kill old instances --
echo [3/4] Cleaning up old instances...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a > nul 2>&1
)
echo  OK: Ports cleared.

:: -- 4. Launch servers --
echo [4/4] Starting servers...
echo.

start "Backend :8000" /d "%BACKEND%" cmd /k "title Backend :8000 && chcp 65001 > nul && venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000 --host 0.0.0.0"
timeout /t 3 /nobreak > nul

start "Frontend :5173" /d "%FRONTEND%" cmd /k "title Frontend :5173 && chcp 65001 > nul && npm run dev"
timeout /t 5 /nobreak > nul

:: -- 5. Open browser --
echo Opening browser...
start "" http://localhost:5173

echo.
echo ============================================
echo   Backend   http://localhost:8000
echo   Frontend  http://localhost:5173
echo ============================================
echo.
echo  Both servers are running in separate windows.
echo  Press any key to close this launcher.
echo  (servers will keep running)
echo.
pause > nul
exit /b 0

:fail
echo.
echo ============================================
echo  Launch failed. See error above.
echo  Press any key to close.
echo ============================================
pause > nul
exit /b 1
