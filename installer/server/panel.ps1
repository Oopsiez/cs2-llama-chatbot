# A small window for the server PC: switch the AI model server on or off, see the address the
# gaming PC should use, and watch who is connected. Needs nothing but Windows PowerShell.
param([int]$Port = 11434)

# Firewall rule and machine-wide settings need admin, so come back elevated if we are not.
$me = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal $me).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", "`"$PSCommandPath`"", "-Port", "$Port"
    )
    exit
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$ruleName = "CS2 Chatbot - Ollama"
$envHost = [Environment]::GetEnvironmentVariable("OLLAMA_HOST", "Machine")
if ($envHost -match ":(\d+)$") { $Port = [int]$Matches[1] }

function Find-Ollama {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe", "$env:ProgramFiles\Ollama\ollama.exe") {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Lan-Address {
    $route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
        Sort-Object RouteMetric, InterfaceMetric | Select-Object -First 1
    if ($route) {
        $ip = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress
        if ($ip) { return $ip }
    }
    (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*"
    } | Select-Object -First 1).IPAddress
}

function Server-Running {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$script:Port/api/tags" -UseBasicParsing -TimeoutSec 2
        return $r.StatusCode -eq 200
    } catch { return $false }
}

function Loaded-Models {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$script:Port/api/ps" -TimeoutSec 2
        return @($r.models | ForEach-Object { $_.name })
    } catch { return @() }
}

function Connections {
    Get-NetTCPConnection -LocalPort $script:Port -State Established -ErrorAction SilentlyContinue |
        Where-Object { $_.RemoteAddress -notlike "127.*" -and $_.RemoteAddress -ne "::1" } |
        Select-Object -ExpandProperty RemoteAddress -Unique
}

function Start-Server {
    $ollama = Find-Ollama
    if (-not $ollama) {
        [System.Windows.Forms.MessageBox]::Show("Ollama is not installed. Run CS2 Chatbot Server Setup again.", "CS2 Chatbot Server") | Out-Null
        return
    }
    $env:OLLAMA_HOST = "0.0.0.0:$script:Port"
    $app = Join-Path (Split-Path $ollama) "ollama app.exe"
    if (Test-Path $app) { Start-Process $app } else { Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden }
}

function Stop-Server {
    Get-Process "ollama app", "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

function Apply-Port([int]$new) {
    $script:Port = $new
    [Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:$new", "Machine")
    Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP `
        -LocalPort $new -Profile Private, Domain | Out-Null
    Stop-Server
    Start-Sleep -Seconds 2
    Start-Server
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "CS2 Chatbot Server"
$form.Size = New-Object System.Drawing.Size(420, 300)
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.StartPosition = "CenterScreen"
$form.Font = New-Object System.Drawing.Font("Segoe UI", 10)

$toggle = New-Object System.Windows.Forms.CheckBox
$toggle.Text = "Run the AI models (Ollama)"
$toggle.Location = New-Object System.Drawing.Point(16, 16)
$toggle.AutoSize = $true
$form.Controls.Add($toggle)

$models = New-Object System.Windows.Forms.Label
$models.Location = New-Object System.Drawing.Point(16, 44)
$models.Size = New-Object System.Drawing.Size(380, 40)
$models.Text = "Checking..."
$form.Controls.Add($models)

$netLabel = New-Object System.Windows.Forms.Label
$netLabel.Text = "Network - the gaming PC connects to:"
$netLabel.Location = New-Object System.Drawing.Point(16, 92)
$netLabel.AutoSize = $true
$form.Controls.Add($netLabel)

$address = New-Object System.Windows.Forms.TextBox
$address.Location = New-Object System.Drawing.Point(16, 116)
$address.Size = New-Object System.Drawing.Size(260, 26)
$address.ReadOnly = $true
$form.Controls.Add($address)

$portLabel = New-Object System.Windows.Forms.Label
$portLabel.Text = "Port"
$portLabel.Location = New-Object System.Drawing.Point(286, 119)
$portLabel.AutoSize = $true
$form.Controls.Add($portLabel)

$portBox = New-Object System.Windows.Forms.TextBox
$portBox.Location = New-Object System.Drawing.Point(324, 116)
$portBox.Size = New-Object System.Drawing.Size(60, 26)
$portBox.Text = "$Port"
$form.Controls.Add($portBox)

$apply = New-Object System.Windows.Forms.Button
$apply.Text = "Apply port (updates the firewall rule)"
$apply.Location = New-Object System.Drawing.Point(16, 148)
$apply.Size = New-Object System.Drawing.Size(368, 28)
$form.Controls.Add($apply)

$connLabel = New-Object System.Windows.Forms.Label
$connLabel.Text = "Connections:"
$connLabel.Location = New-Object System.Drawing.Point(16, 188)
$connLabel.AutoSize = $true
$form.Controls.Add($connLabel)

$conns = New-Object System.Windows.Forms.Label
$conns.Location = New-Object System.Drawing.Point(16, 210)
$conns.Size = New-Object System.Drawing.Size(380, 44)
$conns.Text = "-"
$form.Controls.Add($conns)

$script:busy = $false
$refresh = {
    if ($script:busy) { return }
    $script:busy = $true
    try {
        $up = Server-Running
        $toggle.Checked = $up
        $toggle.Text = if ($up) { "Run the AI models (Ollama) - running" } else { "Run the AI models (Ollama) - stopped" }
        if ($up) {
            $loaded = Loaded-Models
            $models.Text = if ($loaded.Count) { "Loaded: " + ($loaded -join ", ") } else { "No model loaded yet (loads on the first reply)" }
        } else {
            $models.Text = "Server is off - the bot cannot answer."
        }
        $address.Text = "http://$(Lan-Address):$script:Port"
        $who = @(Connections)
        $conns.Text = if ($who.Count) { "$($who.Count) connected: " + ($who -join ", ") } else { "Nobody connected" }
    } finally { $script:busy = $false }
}

$toggle.Add_Click({
    if ($toggle.Checked) { Start-Server } else { Stop-Server }
    Start-Sleep -Seconds 2
    & $refresh
})
$apply.Add_Click({
    $new = 0
    if (-not [int]::TryParse($portBox.Text, [ref]$new) -or $new -lt 1 -or $new -gt 65535) {
        [System.Windows.Forms.MessageBox]::Show("Enter a port between 1 and 65535.", "CS2 Chatbot Server") | Out-Null
        return
    }
    Apply-Port $new
    & $refresh
})

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 3000
$timer.Add_Tick($refresh)
$timer.Start()
$form.Add_Shown({ & $refresh })
[void]$form.ShowDialog()
