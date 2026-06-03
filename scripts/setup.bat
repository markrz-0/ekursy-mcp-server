@echo off
where python >nul 2>nul
if %errorlevel% equ 0 (
    python "%~dp0configure.py"
) else (
    echo Error: Python is not installed or not in PATH. Please install Python.
    pause
)
