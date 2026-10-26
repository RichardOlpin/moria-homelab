@echo off
:: ==============================================================================
:: Moria Homelab - Install 'balrog' Remote Sleep Webhook Service
:: Target: Windows 11 (AMD Ryzen 7 7800X3D + Nvidia GeForce RTX 5070)
:: ==============================================================================

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Administrator permissions required.
    echo Please right-click this .bat file and select 'Run as administrator'.
    pause
    exit /b 1
)

echo.
echo ==============================================================================
echo  Installing Moria Balrog Remote Sleep Webhook (Port 9090)
echo ==============================================================================
echo.

set SCRIPT_DIR=%~dp0
set PS_SCRIPT=%SCRIPT_DIR%sleep-webhook.ps1

:: 1. Open Port 9090 in Windows Firewall
echo [1/3] Adding Windows Firewall rule for Port 9090 (TCP Inbound)...
netsh advfirewall firewall delete rule name="Balrog-Sleep-Webhook" >nul 2>&1
netsh advfirewall firewall add rule name="Balrog-Sleep-Webhook" dir=in action=allow protocol=TCP localport=9090 profile=any >nul
echo       Firewall rule created successfully.

:: 2. Grant URL ACL permission for port 9090
echo [2/3] Configuring URL ACL reservation for http://+:9090/...
netsh http delete urlacl url=http://+:9090/ >nul 2>&1
netsh http add urlacl url=http://+:9090/ user="Everyone" >nul 2>&1

:: 3. Register Scheduled Task to launch at startup
echo [3/3] Registering Scheduled Task 'Moria-Balrog-Sleep-Service'...
schtasks /delete /tn "Moria-Balrog-Sleep-Service" /f >nul 2>&1
schtasks /create /tn "Moria-Balrog-Sleep-Service" ^
    /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%PS_SCRIPT%\"" ^
    /sc onstart /delay 0000:15 /rl HIGHEST /ru "SYSTEM" /f >nul

if %errorLevel% equ 0 (
    echo.
    echo ==============================================================================
    echo  SUCCESS: Balrog Instant Sleep Webhook installed!
    echo  Starting service now...
    echo ==============================================================================
    schtasks /run /tn "Moria-Balrog-Sleep-Service" >nul 2>&1
) else (
    echo [ERROR] Failed to register scheduled task.
)

echo.
echo Test from strider or erebor with:
echo   curl http://192.168.0.40:9090/status
echo   curl -X POST http://192.168.0.40:9090/sleep
echo.
pause
