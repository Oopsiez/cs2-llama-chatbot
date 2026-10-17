# Undoes install.ps1's network changes. Ollama itself stays installed (Add/Remove Programs).
$ErrorActionPreference = "SilentlyContinue"
Get-NetFirewallRule -DisplayName "CS2 Chatbot - Ollama" | Remove-NetFirewallRule
Get-NetFirewallRule -DisplayName "CS2 Chatbot - Update agent" | Remove-NetFirewallRule
Stop-ScheduledTask -TaskName "CS2 Chatbot Server Agent"
Unregister-ScheduledTask -TaskName "CS2 Chatbot Server Agent" -Confirm:$false
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", $null, "Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", $null, "Machine")
Write-Host "Firewall rule and network settings removed; Ollama is back to localhost only."
