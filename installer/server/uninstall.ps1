# Undoes install.ps1's network changes. Ollama itself stays installed (Add/Remove Programs).
$ErrorActionPreference = "SilentlyContinue"
Get-NetFirewallRule -DisplayName "CS2 Chatbot - Ollama" | Remove-NetFirewallRule
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", $null, "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", $null, "Machine")
Write-Host "Firewall rule and network settings removed; Ollama is back to localhost only."
