<#
.SYNOPSIS
    'balrog' Windows Auto-Sleep Idle Watcher (AMD Ryzen 7 7800X3D + Nvidia RTX 5070)
.DESCRIPTION
    Monitors user activity (keyboard/mouse) and Nvidia GPU utilization.
    When balrog is woken via Wake-on-LAN for an LM Studio / Ollama / Immich ML job,
    this daemon ensures the PC automatically suspends back to sleep after $IdleMinutes
    of inactivity and low GPU usage (<10%), dropping power from ~100W down to ~2W.
#>

[CmdletBinding()]
param(
    [int]$IdleMinutes = 20,
    [int]$GpuThreshold = 10,
    [int]$CheckIntervalSeconds = 60
)

# Win32 API to detect physical mouse / keyboard idle time
Add-Type @'
using System;
using System.Runtime.InteropServices;

public class UserInput {
    [StructLayout(LayoutKind.Sequential)]
    struct LASTINPUTINFO {
        public static readonly int SizeOf = Marshal.SizeOf(typeof(LASTINPUTINFO));
        [MarshalAs(UnmanagedType.U4)]
        public UInt32 cbSize;
        [MarshalAs(UnmanagedType.U4)]
        public UInt32 dwTime;
    }

    [DllImport("user32.dll")]
    static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);

    public static double GetIdleMinutes() {
        LASTINPUTINFO info = new LASTINPUTINFO();
        info.cbSize = (uint)Marshal.SizeOf(info);
        if (GetLastInputInfo(ref info)) {
            uint idleTicks = (uint)Environment.TickCount - info.dwTime;
            return TimeSpan.FromMilliseconds(idleTicks).TotalMinutes;
        }
        return 0;
    }
}
'@

Add-Type -AssemblyName System.Windows.Forms

Write-Host "==============================================================================" -ForegroundColor DarkYellow
Write-Host " 🔥 Moria Homelab: balrog Auto-Sleep Watcher Active" -ForegroundColor Yellow
Write-Host "    Target: AMD 7800X3D + Nvidia RTX 5070" -ForegroundColor Gray
Write-Host "    Idle Threshold: $IdleMinutes minutes with GPU < $GpuThreshold%" -ForegroundColor Gray
Write-Host "==============================================================================" -ForegroundColor DarkYellow

$consecutiveIdleMinutes = 0

while ($true) {
    Start-Sleep -Seconds $CheckIntervalSeconds

    # 1. Query Nvidia GPU utilization via nvidia-smi
    $gpuUtil = 0
    try {
        $smiOut = & nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>$null
        if ($smiOut) {
            $gpuUtil = [int]($smiOut.Trim().Split("`n")[0])
        }
    } catch {
        $gpuUtil = 0
    }

    # 2. Query physical user idle minutes (keyboard/mouse)
    $userIdleMinutes = [UserInput]::GetIdleMinutes()

    $isGpuBusy = $gpuUtil -ge $GpuThreshold
    $isUserActive = $userIdleMinutes -lt 2.0

    if ($isGpuBusy -or $isUserActive) {
        if ($consecutiveIdleMinutes -gt 0) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Activity detected (GPU: $gpuUtil%, User idle: $([math]::Round($userIdleMinutes, 1))m). Resetting idle timer." -ForegroundColor Cyan
        }
        $consecutiveIdleMinutes = 0
    } else {
        $consecutiveIdleMinutes++
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Idle minute $consecutiveIdleMinutes/$IdleMinutes (GPU: $gpuUtil%, User idle: $([math]::Round($userIdleMinutes, 1))m)" -ForegroundColor Gray
    }

    # 3. If idle threshold reached, suspend back to sleep
    if ($consecutiveIdleMinutes -ge $IdleMinutes) {
        Write-Host "==> 'balrog' has been idle for $IdleMinutes minutes. Returning to the shadow (suspending)..." -ForegroundColor Yellow
        $consecutiveIdleMinutes = 0
        Start-Sleep -Seconds 2
        [System.Windows.Forms.Application]::SetSuspendState([System.Windows.Forms.PowerState]::Suspend, $false, $false)
    }
}
