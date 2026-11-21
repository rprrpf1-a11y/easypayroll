@echo off
title EasyPayroll System
cd /d "%~dp0"
echo ============================================================
echo  Starting EasyPayroll Production Server...
echo  Local URL: http://127.0.0.1:5000
echo  Press Ctrl+C to stop the server anytime.
echo ============================================================
python run_production.py
pause
