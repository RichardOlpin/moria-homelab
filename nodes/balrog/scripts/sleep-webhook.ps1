param(
    [int]$Port = 9090
)

Add-Type -AssemblyName System.Windows.Forms

Write-Host "==============================================================================" -ForegroundColor DarkYellow
Write-Host " 🔥 Moria Homelab: balrog Instant Sleep Webhook Active (Port $Port)" -ForegroundColor Yellow
Write-Host "    Target: AMD 7800X3D + Nvidia RTX 5070" -ForegroundColor Gray
Write-Host "==============================================================================" -ForegroundColor DarkYellow

$listener = New-Object System.Net.HttpListener
$prefix = "http://+:$Port/"

try {
    $listener.Prefixes.Add($prefix)
    $listener.Start()
    Write-Host "Webhook listener bound successfully to $prefix" -ForegroundColor Green
} catch {
    Write-Host "Falling back to http://*:$Port/ ..." -ForegroundColor Yellow
    $listener = New-Object System.Net.HttpListener
    $listener.Prefixes.Add("http://*:$Port/")
    $listener.Start()
}

Write-Host "Ready for remote sleep commands on port $Port..." -ForegroundColor Cyan

while ($listener.IsListening) {
    try {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response
        $url = $request.RawUrl.ToLower()

        $response.AddHeader("Access-Control-Allow-Origin", "*")
        $response.AddHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        if ($request.HttpMethod -eq "OPTIONS") {
            $response.StatusCode = 204
            $response.Close()
            continue
        }

        if ($url -eq "/health" -or $url -eq "/status") {
            $msg = '{"status":"online","node":"balrog"}'
            $buf = [System.Text.Encoding]::UTF8.GetBytes($msg)
            $response.ContentType = "application/json"
            $response.ContentLength64 = $buf.Length
            $response.StatusCode = 200
            $response.OutputStream.Write($buf, 0, $buf.Length)
            $response.Close()
            continue
        }

        if ($url -eq "/sleep") {
            Write-Host "Remote sleep signal received! Suspending balrog to S3..." -ForegroundColor Red
            $msg = '{"status":"suspending","node":"balrog"}'
            $buf = [System.Text.Encoding]::UTF8.GetBytes($msg)
            $response.ContentType = "application/json"
            $response.ContentLength64 = $buf.Length
            $response.StatusCode = 200
            $response.OutputStream.Write($buf, 0, $buf.Length)
            $response.Close()

            Start-Sleep -Milliseconds 500
            [System.Windows.Forms.Application]::SetSuspendState([System.Windows.Forms.PowerState]::Suspend, $false, $false)
            continue
        }

        $response.StatusCode = 404
        $response.Close()
    } catch {
        Write-Host "Listener notice: $_" -ForegroundColor DarkGray
    }
}
