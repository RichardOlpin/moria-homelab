$s = New-Object System.Net.HttpListener
$s.Prefixes.Add('http://+:9090/')
$s.Start()
Write-Host 'Balrog Sleep Listener online on port 9090'
while ($s.IsListening) {
    $c = $s.GetContext()
    if ($c.Request.RawUrl -eq '/sleep') {
        $b = [System.Text.Encoding]::UTF8.GetBytes('sleeping')
        $c.Response.OutputStream.Write($b, 0, $b.Length)
        $c.Response.Close()
        Start-Sleep -Milliseconds 500
        rundll32.exe powrprof.dll,SetSuspendState 0,1,0
    } else {
        $b = [System.Text.Encoding]::UTF8.GetBytes('online')
        $c.Response.OutputStream.Write($b, 0, $b.Length)
        $c.Response.Close()
    }
}
