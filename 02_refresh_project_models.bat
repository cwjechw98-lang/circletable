@echo off
setlocal EnableExtensions
chcp 65001 > nul 2>&1
title Refresh Project Models

echo ============================================
echo   Refresh Project Models
echo ============================================
echo.
echo Sending a refresh command to the running project...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0refresh_project_models.ps1"
if errorlevel 1 goto :refresh_failed

echo.
echo If the app is open in the browser, the model list should now be refreshed.
exit /b 0

:refresh_failed
echo ERROR: Could not refresh the model list.
echo Start the project first with start.bat or 03_start_round_table.bat.
exit /b 1
