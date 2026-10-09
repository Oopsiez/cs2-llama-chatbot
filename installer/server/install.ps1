# Sets up a Windows PC on your LAN as the brain for the CS2 Chatbot: installs Ollama if it is
# missing, makes it listen on the network, opens the firewall for the private network only, and
# pulls the chat model. Run as administrator. Re-running is safe.
param(
    [string]$Model = "hf.co/Andycurrent/Llama-3-8B-Lexi-Uncensored:Q4_K_M",
    [int]$Port = 11434
)
$ErrorActionPreference = "Stop"
$me = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal $me).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Restarting as administrator (the firewall rule and Ollama setup need it)..."
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-File", "`"$PSCommandPath`"",
        "-Model", "`"$Model`"", "-Port", "$Port"
    )
    exit
}
$ruleName = "CS2 Chatbot - Ollama"

function Find-Ollama {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $local = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $local) { return $local }
    return $null
}

$ollama = Find-Ollama
if (-not $ollama) {
    $setup = Join-Path $env:TEMP "OllamaSetup.exe"
    $url = "https://ollama.com/download/OllamaSetup.exe"
    Write-Host "Ollama is not installed - downloading it (about 1 GB, this takes a few minutes)..."
    $downloaded = $false
    try {
        Import-Module BitsTransfer -ErrorAction Stop
        Start-BitsTransfer -Source $url -Destination $setup -DisplayName "Ollama" -Description "Downloading Ollama"
        $downloaded = Test-Path $setup
    } catch {
        Write-Host "  (BITS unavailable: $($_.Exception.Message) - falling back to a plain download)"
    }
    if (-not $downloaded) {
        $client = New-Object System.Net.WebClient
        $last = [DateTime]::MinValue
        Register-ObjectEvent $client DownloadProgressChanged -SourceIdentifier OllamaDl -Action {
            if (([DateTime]::Now - $Event.MessageData.Value).TotalSeconds -ge 2) {
                $mb = [math]::Round($EventArgs.BytesReceived / 1MB)
                $total = [math]::Round($EventArgs.TotalBytesToReceive / 1MB)
                Write-Host ("`r  {0} MB of {1} MB ({2}%)" -f $mb, $total, $EventArgs.ProgressPercentage) -NoNewline
                $Event.MessageData.Value = [DateTime]::Now
            }
        } -MessageData ([ref]$last) | Out-Null
        $done = Register-ObjectEvent $client DownloadFileCompleted -SourceIdentifier OllamaDone
        $client.DownloadFileAsync([Uri]$url, $setup)
        Wait-Event -SourceIdentifier OllamaDone | Out-Null
        Unregister-Event OllamaDl; Unregister-Event OllamaDone
        Write-Host ""
    }
    if (-not (Test-Path $setup) -or (Get-Item $setup).Length -lt 100MB) {
        Write-Host "The download did not finish. Install Ollama by hand from https://ollama.com/download and run this setup again."
        exit 1
    }
    Write-Host "Installing Ollama..."
    Start-Process $setup -ArgumentList "/VERYSILENT", "/NORESTART" -Wait
    $ollama = Find-Ollama
    if (-not $ollama) { throw "Ollama did not install; run $setup by hand and try again" }
}
Write-Host "Ollama: $ollama"

# Listen on every interface so the gaming PC can reach it, and keep the model warm between rounds.
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:$Port", "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "30m", "Machine")
$env:OLLAMA_HOST = "0.0.0.0:$Port"

# Private and domain profiles only - never the public profile, so a laptop on hotel wifi stays shut.
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP `
    -LocalPort $Port -Profile Private, Domain | Out-Null
Write-Host "Firewall: TCP $Port open on the private network"

# Restart Ollama so it picks up the new host setting (the tray app relaunches at login on its own).
Get-Process "ollama app", "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$app = Join-Path (Split-Path $ollama) "ollama app.exe"
if (Test-Path $app) { Start-Process $app } else { Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden }
Start-Sleep -Seconds 5

Write-Host "Pulling $Model (about 5 GB, once)..."
& $ollama pull $Model
if ($LASTEXITCODE -ne 0) { throw "ollama pull failed" }

# The address the game PC can reach: the adapter that carries the default route, not a
# Hyper-V / VPN / Docker adapter that happens to be listed first.
$ip = $null
$route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
    Sort-Object RouteMetric, InterfaceMetric | Select-Object -First 1
if ($route) {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress
}
if (-not $ip) {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.PrefixOrigin -ne "WellKnown"
    } | Select-Object -First 1).IPAddress
}
$others = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne $ip -and $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" }).IPAddress
if ($others) { Write-Host "Other addresses on this PC (use one of these if the game PC cannot reach the one below): $($others -join ', ')" }
Write-Host ""
Write-Host "Done. On the gaming PC, open the bot's Model tab -> 'Use a server on my network' and enter:"
Write-Host "    http://${ip}:$Port"
Write-Host "Model: $Model"
