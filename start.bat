@echo off
setlocal EnableExtensions
chcp 65001 > nul 2>&1
title Start AI Round Table

echo ============================================
echo   Preparing AI Round Table
echo ============================================
echo.

call "%~dp000_check_ollama.bat"
if errorlevel 1 (
    echo.
    echo WARNING: Ollama is not available.
    echo The project can still start, but local models will not work.
    choice /C YN /M "Start the project without Ollama?"
    if errorlevel 2 exit /b 1
    goto :start_project
)

echo.
call "%~dp001_prepare_ollama_models.bat"
if errorlevel 1 (
    echo.
    echo WARNING: Local model setup did not finish successfully.
    choice /C YN /M "Start the project with the current Ollama state?"
    if errorlevel 2 exit /b 1
)

:start_project
echo.
echo Starting the project...
call "%~dp0start_core.bat"
exit /b %errorlevel%
