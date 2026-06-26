@echo off
REM Image2 MCP — Double-Click Setup for Windows
REM Just double-click this file in Explorer.
cd /d "%~dp0"
echo Starting Image2 MCP Setup...
echo.

REM Try Git Bash first, then WSL, then plain bash
where git >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    for /f "delims=" %%i in ('where git') do set GIT_DIR=%%~dpi
    set GIT_BASH=%GIT_DIR%..\bin\bash.exe
    if exist "%GIT_BASH%" (
        echo Using Git Bash...
        "%GIT_BASH%" scripts/setup.sh
        goto :done
    )
)

where wsl >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Using WSL...
    wsl bash scripts/setup.sh
    goto :done
)

where bash >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Using bash...
    bash scripts/setup.sh
    goto :done
)

echo.
echo ERROR: No bash shell found. Please install Git for Windows:
echo   https://git-scm.com/download/win
echo Or install WSL:
echo   wsl --install

:done
echo.
pause
