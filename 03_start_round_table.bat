@echo off
setlocal EnableExtensions
chcp 65001 > nul 2>&1
title Start AI Round Table Alias

echo ============================================
echo   Redirecting to start.bat
echo ============================================
echo.
call "%~dp0start.bat"
exit /b %errorlevel%
