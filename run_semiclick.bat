@echo off
setlocal

cd /d "%~dp0"

set "VENV_DIR=%CD%\.venv"
set "FIRST_SETUP=0"

if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv "%VENV_DIR%"
  if errorlevel 1 goto :fail
  set "FIRST_SETUP=1"
)

echo Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 goto :fail

if "%FIRST_SETUP%"=="1" (
  echo Upgrading pip...
  python -m pip install --upgrade pip
  if errorlevel 1 goto :fail
)

echo Ensuring dependencies are installed...
python -m pip install -r "%CD%\requirements.txt"
if errorlevel 1 goto :fail

set "PYTHONPATH=%CD%\src"

echo Launching semiCLICK...
python -m semiclick
set "APP_EXIT_CODE=%ERRORLEVEL%"

if exist "%VENV_DIR%\Scripts\deactivate.bat" (
  call "%VENV_DIR%\Scripts\deactivate.bat"
)

exit /b %APP_EXIT_CODE%

:fail
echo.
echo semiCLICK failed to start.
echo Check the error above and confirm that Python is installed and available on PATH.
exit /b 1
