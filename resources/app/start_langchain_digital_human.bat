@echo off
setlocal
cd /d "%~dp0"

python "%~dp0start_langchain_digital_human.py"
if errorlevel 1 (
  echo.
  echo Startup failed. Please check the error above.
  pause
)
