@echo off
setlocal
title Build Shadow Relic 32 - Windows x86
cd /d "%~dp0"
python -c "import struct,sys; bits=struct.calcsize('P')*8; print('Python architecture:',bits,'bit'); sys.exit(0 if bits==32 else 3)"
if errorlevel 1 (
  echo.
  echo TRUE 32-bit EXE requires a 32-bit Python installation with compatible SwirEngine dependencies.
  echo Re-run this script from that x86 Python environment.
  pause
  exit /b 1
)
set "SHADOW_RELIC_ASSET_CACHE=%CD%\build_assets"
python procedural_art.py || goto :fail
python -m pip install -U pyinstaller || goto :fail
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --collect-all glfw --collect-all glcontext --collect-all swirengine ^
  --icon "%SHADOW_RELIC_ASSET_CACHE%\shadow_relic_32.ico" ^
  --name ShadowRelic32 main.py || goto :fail
echo.
echo Built: dist\ShadowRelic32.exe
pause
exit /b 0
:fail
echo.
echo Build failed.
pause
exit /b 1
