@echo off
title Neon Robo Rush v9 - 32-Bit Edition
cd /d "%~dp0"
python -c "import swirengine; print('Using SwirEngine', swirengine.__version__)" || (
 echo.
 echo SwirEngine is missing.
 echo Install: python -m pip install -U "swirengine==2.0.0"
 pause
 exit /b 1
)
python main.py
if errorlevel 1 pause
