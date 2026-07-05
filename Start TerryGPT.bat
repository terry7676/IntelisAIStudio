@echo off
cd /d "%~dp0"

call .venv\Scripts\activate.bat

python main.py

echo.
echo ==========================
echo TerryGPT exited.
echo Press any key to close...
pause