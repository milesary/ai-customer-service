@echo off
chcp 65001 >nul
"%~dp0backend\.venv\Scripts\python.exe" "%~dp0start.py"
if errorlevel 1 pause
