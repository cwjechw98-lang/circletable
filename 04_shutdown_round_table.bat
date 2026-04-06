@echo off
chcp 65001 > nul 2>&1
title Shutdown AI Round Table

powershell -ExecutionPolicy Bypass -File "%~dp0shutdown_round_table.ps1"
