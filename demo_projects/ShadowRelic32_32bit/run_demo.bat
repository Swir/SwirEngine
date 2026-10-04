@echo off
setlocal
title Shadow Relic 32 - SwirEngine 2.2 Adventure
cd /d "%~dp0"
python -c "import swirengine; print('Using SwirEngine', swirengine.__version__)" || (
  echo.
  echo SwirEngine is missing.
  echo Install from the repository or: python -m pip install -U "swirengine>=2.2,<3.0"
  pause
  exit /b 1
)
python main.py
if errorlevel 1 pause
