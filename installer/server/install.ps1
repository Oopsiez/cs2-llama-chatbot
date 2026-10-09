# Sets up a Windows PC on your LAN as the brain for the CS2 Chatbot: installs Ollama if it is
# missing, makes it listen on the network, opens the firewall for the private network only, and
# pulls the chat model. Run as administrator. Re-running is safe.
param(
    [string]$Model = "hf.co/Andycurrent/Llama-3-8B-Lexi-Uncensored:Q4_K_M",
    [int]$Port = 11434
)
$ErrorActionPreference = "Stop"
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
    Write-Host "Ollama is not installed - downloading it..."
    $setup = Join-Path $env:TEMP "OllamaSetup.exe"
    Invoke-WebRequest "https://ollama.com/download/OllamaSetup.exe" -OutFile $setup -UseBasicParsing
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

$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
Write-Host ""
Write-Host "Done. On the gaming PC, open the bot's Model tab -> 'Use a server on my network' and enter:"
Write-Host "    http://${ip}:$Port"
Write-Host "Model: $Model"
