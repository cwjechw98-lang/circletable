@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 > nul 2>&1
title Ollama Model Setup

call "%~dp000_check_ollama.bat"
if errorlevel 1 exit /b 1

set "OLLAMA_CMD="
if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_CMD=%ProgramFiles%\Ollama\ollama.exe"
if not defined OLLAMA_CMD if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_CMD=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_CMD (
    for %%I in (ollama.exe) do set "OLLAMA_CMD=%%~$PATH:I"
)

set "RECOMMENDED_MODEL="
set /a MODEL_COUNT=0

for /f "skip=1 tokens=1" %%M in ('"%OLLAMA_CMD%" list 2^>nul') do (
    if /I not "%%M"=="NAME" (
        set /a MODEL_COUNT+=1
        if not defined RECOMMENDED_MODEL (
            if /I "%%M"=="deepseek-r1" set "RECOMMENDED_MODEL=deepseek-r1"
            if /I "%%M"=="qwen3:4b" set "RECOMMENDED_MODEL=qwen3:4b"
            if /I "%%M"=="qwen3" set "RECOMMENDED_MODEL=qwen3"
            if /I "%%M"=="gemma3:4b" set "RECOMMENDED_MODEL=gemma3:4b"
            if /I "%%M"=="gemma3" set "RECOMMENDED_MODEL=gemma3"
            if /I "%%M"=="llama3.2" set "RECOMMENDED_MODEL=llama3.2"
        )
    )
)

echo ============================================
echo   Ollama Model Setup
echo ============================================
echo.

if defined RECOMMENDED_MODEL (
    echo A recommended local model is already installed: !RECOMMENDED_MODEL!
    echo No extra download is needed.
    exit /b 0
)

if !MODEL_COUNT! GTR 0 (
    echo Local models already exist, but the recommended starter model was not found.
    echo The project will still detect all installed models automatically.
    echo If you want a stronger starter option later, run:
    echo    ollama pull gemma3:4b
    exit /b 0
)

echo No local models were found.
echo Trying to install the default starter model: gemma3:4b
"%OLLAMA_CMD%" pull gemma3:4b
if not errorlevel 1 (
    echo.
    echo OK: gemma3:4b was installed.
    exit /b 0
)

echo.
echo INFO: Could not install gemma3:4b.
echo Trying a lighter fallback: llama3.2
"%OLLAMA_CMD%" pull llama3.2
if not errorlevel 1 (
    echo.
    echo OK: llama3.2 was installed.
    exit /b 0
)

echo.
echo ERROR: Could not install any starter model.
echo Check your internet connection and Ollama Library availability, then try again.
exit /b 1
