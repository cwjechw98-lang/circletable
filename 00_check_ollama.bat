@echo off
setlocal EnableExtensions
chcp 65001 > nul 2>&1
title Ollama Check

set "OLLAMA_CMD="

if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_CMD=%ProgramFiles%\Ollama\ollama.exe"
if not defined OLLAMA_CMD if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_CMD=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_CMD (
    for %%I in (ollama.exe) do set "OLLAMA_CMD=%%~$PATH:I"
)

if not defined OLLAMA_CMD goto :not_found

echo ============================================
echo   Ollama Check
echo ============================================
echo.
echo [1/3] Found executable:
echo %OLLAMA_CMD%
echo.
"%OLLAMA_CMD%" --version
if errorlevel 1 goto :version_failed

echo.
echo [2/3] Checking local API at http://localhost:11434 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo INFO: Ollama is installed, but the local API is not responding yet.
    if exist "%LOCALAPPDATA%\Programs\Ollama\Ollama.exe" (
        echo INFO: Trying to launch the Ollama app...
        start "" "%LOCALAPPDATA%\Programs\Ollama\Ollama.exe"
        timeout /t 6 /nobreak > nul
        powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }"
        if errorlevel 1 goto :api_failed
    ) else (
        goto :api_failed
    )
)

echo.
echo [3/3] Current local models:
"%OLLAMA_CMD%" list
echo.
echo OK: Ollama is ready for this project.
exit /b 0

:not_found
echo ERROR: Ollama was not found on this computer.
echo Install it before starting the project:
echo https://ollama.com/download/windows
exit /b 1

:version_failed
echo ERROR: ollama --version failed.
exit /b 1

:api_failed
echo ERROR: Could not reach the local Ollama API.
echo Open the Ollama app manually and run this check again.
exit /b 1
