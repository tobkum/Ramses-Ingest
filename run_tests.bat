@echo off
setlocal

:: Get the directory where the batch file is located
set "PROJECT_ROOT=%~dp0"

:: Set PYTHONPATH to include the lib directory (vendored ramses)
set "PYTHONPATH=%PROJECT_ROOT%;%PROJECT_ROOT%lib;%PYTHONPATH%"

echo [Ramses-Ingest] Running test suite...
echo.

python -m unittest discover -v tests

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Some tests failed!
    exit /b %ERRORLEVEL%
)

echo.
echo [SUCCESS] All tests passed.
pause
