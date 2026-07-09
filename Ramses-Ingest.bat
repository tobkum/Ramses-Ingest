@echo off
setlocal

:: Launch Ramses-Ingest from its project directory
pushd "%~dp0"

python -m ramses_ingest
set "EXITCODE=%ERRORLEVEL%"

popd

if %EXITCODE% neq 0 (
    echo.
    echo [Ramses-Ingest] exited with error code %EXITCODE%.
    pause
)

endlocal
