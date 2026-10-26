<#
.SYNOPSIS
    'balrog' Instant Remote Sleep Webhook Service (Moria Homelab)
.DESCRIPTION
    Runs an ultra-lightweight HTTP listener on port 9090.
    Accepts remote sleep requests from Palantír, strider, or erebor:
      POST http://<balrog-ip>:9090/sleep
    Immediately suspends the PC to ACPI S3 Standby/Sleep (~2W) without waiting for idle timeouts.
#>

[CmdletBinding()]
param(
    [int]$Port = 9090
)

Add-Type -AssemblyName System.Windows.Forms

Write-Host "==============================================================================" -ForegroundColor DarkYellow
Write-Host " 🔥 Moria Homelab: balrog Instant Sleep Webhook Active" -ForegroundColor Yellow
Write-Host "    Listening on: http://*:$Port/sleep" -ForegroundColor Cyan
Write-Host "    Target: AMD 7800X3D + Nvidia RTX 5070" -ForegroundColor Gray
Write-Host "==============================================================================" -ForegroundColor DarkYellow

$listener = New-Object System.Net.HttpListener
$prefix = "http://+:$Port/"

try {
    $listener.Prefixes.Add($prefix)
    $listener.Start()
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Webhook listener bound successfully to $prefix" -ForegroundColor Green
} catch {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Falling back to localhost/IP binding: $_" -ForegroundColor Yellow
    $listener = New-Object System.Net.HttpListener
    $listener.Prefixes.Add("http://*:$Port/")
    $listener.Start()
}

$startTime = Get-Date

while ($listener.IsListening) {
    try {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response
        $rawUrl = $request.RawUrl.ToLower()

        # Add CORS headers for Palantír dashboard
        $response.AddHeader("Access-Control-Allow-Origin", "*")
        $response.AddHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        $response.AddHeader("Access-Control-Allow-Headers", "Content-Type")

        if ($request.HttpMethod -eq "OPTIONS") {
            $response.StatusCode = 204
            $response.Close()
            continue
        }

        # Health / Status probe
        if ($rawUrl -eq "/health" -or $rawUrl -eq "/status") {
            $uptime = ((Get-Date) - $startTime).TotalSeconds
            $json = @{
                status = "online"
                node = "balrog"
                uptime_seconds = [math]::Round($uptime, 1)
                timestamp = (Get-Date).ToString("o")
            } | ConvertTo-Json
            $buffer = [System.Text.Encoding]::UTF8.GetBytes($json)
            $response.ContentType = "application/json"
            $response.ContentLength64 = $buffer.Length
            $response.StatusCode = 200
            $response.OutputStream.Write($buffer, 0, $buffer.Length)
            $response.Close()
            continue
        }

        # Sleep command
        if ($rawUrl -eq "/sleep") {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Remote sleep signal received from $($request.RemoteEndPoint)!" -ForegroundColor Red
            
            $json = @{
                status = "suspending"
                node = "balrog"
                message = "Returning to the shadow (S3 sleep initiated)..."
                timestamp = (Get-Date).ToString("o")
            } | ConvertTo-Json

            $buffer = [System.Text.Encoding]::UTF8.GetBytes($json)
            $response.ContentType = "application/json"
            $response.ContentLength64 = $buffer.Length
            $response.StatusCode = 200
            $response.OutputStream.Write($buffer, 0, $buffer.Length)
            $response.Close()

            # Small delay to ensure HTTP packet is delivered before interface suspends
            Start-Sleep -Milliseconds 600

            Write-Host "==> Entering S3 Suspend state now." -ForegroundColor DarkYellow
            [System.Windows.Forms.Application]::SetSuspendState([System.Windows.Forms.PowerState]::Suspend, $false, $false)
            continue
        }

        # 404 for unknown endpoints
        $response.StatusCode = 404
        $buffer = [System.Text.Encoding]::UTF8.GetBytes('{"error": "not_found"}')
        $response.ContentType = "application/json"
        $response.ContentLength64 = $buffer.Length
        $response.OutputStream.Write($buffer, 0, $buffer.Length)
        $response.Close()
    } catch {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Listener error: $_" -ForegroundColor DarkGray
    }
}
