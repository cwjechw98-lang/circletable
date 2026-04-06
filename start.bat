@echo off
setlocal EnableExtensions
chcp 65001 > nul 2>&1
title Start AI Round Table

echo ============================================
echo   Подготовка «Круглого стола ИИ»
echo ============================================
echo.

call "%~dp000_check_ollama.bat"
if errorlevel 1 (
    echo.
    echo ВНИМАНИЕ: Ollama не найдена или не отвечает.
    echo Проект всё равно можно запустить, но локальные модели работать не будут.
    choice /C YN /M "Запустить проект без Ollama?"
    if errorlevel 2 exit /b 1
    goto :start_project
)

echo.
call "%~dp001_prepare_ollama_models.bat"
if errorlevel 1 (
    echo.
    echo ВНИМАНИЕ: Подготовка локальной модели завершилась не полностью.
    choice /C YN /M "Запустить проект с текущим состоянием Ollama?"
    if errorlevel 2 exit /b 1
)

:start_project
echo.
echo Запускаем проект...
call "%~dp0start_core.bat"
exit /b %errorlevel%
