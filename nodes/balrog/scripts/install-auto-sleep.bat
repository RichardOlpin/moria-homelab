@echo off
:: ==============================================================================
:: Moria Homelab — Install balrog Auto-Sleep Scheduled Task on Windows
:: Registers auto-sleep-watcher.ps1 to start invisibly at system boot.
:: ==============================================================================
setlocal EnableDelayedExpansion

echo ==============================================================================
echo  Installing Moria balrog Auto-Sleep Watcher (AMD 7800X3D + RTX 5070)
echo ==============================================================================

set SCRIPT_DIR=%~dp0
set PS_SCRIPT=%SCRIPT_DIR%auto-sleep-watcher.ps1

if not exist "%PS_SCRIPT%" (
    echo [ERROR] Could not find %PS_SCRIPT%
    pause
    exit /b 1
)

:: Register Scheduled Task with Windows Task Scheduler
schtasks /create /tn "MoriaBalrogAutoSleep" /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%PS_SCRIPT%\"" /sc onlogon /rl highest /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] Scheduled Task 'MoriaBalrogAutoSleep' created successfully!
    echo It will start silently in the background whenever you log into Windows.
    echo.
    echo Starting the watcher right now...
    schtasks /run /tn "MoriaBalrogAutoSleep"
) else (
    echo.
    echo [WARNING] Failed to register scheduled task. Make sure to right-click this batch file
    echo and select 'Run as Administrator'.
)

pause
