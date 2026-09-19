@echo off
setlocal
set "PYTHON=%USERPROFILE%\wxauto-test\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo [ERROR] wxauto4 Python not found: %PYTHON%
  pause
  exit /b 1
)
"%PYTHON%" "%~dp0bridge.py" --poll --once --prompt-access-token
if errorlevel 1 pause
endlocal
