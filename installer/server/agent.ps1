# The server's update agent: a tiny HTTP service on the LAN that tells the gaming PC which
# version of CS2 Chatbot Server is installed and, when asked, downloads and installs another
# release. Runs at logon as a scheduled task (elevated, so the installer can run silently).
param([int]$Port = 11435)

$ErrorActionPreference = "Stop"
$repo = "Oopsiez/cs2-llama-chatbot"
$regKey = "HKLM:\Software\CS2 Chatbot Server"
$state = Join-Path $env:ProgramData "CS2 Chatbot Server"
New-Item -ItemType Directory -Force -Path $state | Out-Null
$log = Join-Path $state "update.log"
$lock = Join-Path $state "updating"
$appDir = $PSScriptRoot

function Installed-Version {
    try { (Get-ItemProperty $regKey -ErrorAction Stop).Version } catch { "unknown" }
}

function Json($obj) { $obj | ConvertTo-Json -Compress }

function Respond($ctx, [int]$code, $obj) {
    $bytes = [Text.Encoding]::UTF8.GetBytes((Json $obj))
    $ctx.Response.StatusCode = $code
    $ctx.Response.ContentType = "application/json"
    $ctx.Response.ContentLength64 = $bytes.Length
    $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    $ctx.Response.Close()
}

function Start-Update([string]$version) {
    # Hand the work to a separate process: the installer replaces this very script, so the
    # agent gets out of the way and the scheduled task brings the new one back afterwards.
    $tag = if ($version.StartsWith("v")) { $version } else { "v$version" }
    $url = "https://github.com/$repo/releases/download/$tag/CS2.Chatbot.Server.Setup.exe"
    Set-Content $lock $tag
    $script = @"
`$ErrorActionPreference = 'Stop'
`$log = '$log'
try {
  Add-Content `$log "`$(Get-Date -Format s) downloading $url"
  `$setup = Join-Path `$env:TEMP 'CS2.Chatbot.Server.Setup.exe'
  Invoke-WebRequest -Uri '$url' -OutFile `$setup -UseBasicParsing
  Add-Content `$log "`$(Get-Date -Format s) installing"
  Start-Process `$setup -ArgumentList '/VERYSILENT','/NORESTART','/SUPPRESSMSGBOXES' -Wait
  Add-Content `$log "`$(Get-Date -Format s) running install.ps1"
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '$appDir\install.ps1' *>> `$log
  Add-Content `$log "`$(Get-Date -Format s) done: $tag"
} catch {
  Add-Content `$log "`$(Get-Date -Format s) failed: `$_"
} finally {
  Remove-Item '$lock' -ErrorAction SilentlyContinue
  Start-ScheduledTask -TaskName 'CS2 Chatbot Server Agent' -ErrorAction SilentlyContinue
}
"@
    $file = Join-Path $state "run-update.ps1"
    Set-Content $file $script
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$file`""
}

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://+:$Port/")
$listener.Start()
Add-Content $log "$(Get-Date -Format s) agent $(Installed-Version) listening on $Port"

while ($listener.IsListening) {
    $ctx = $listener.GetContext()
    $path = $ctx.Request.Url.AbsolutePath.TrimEnd("/")
    try {
        if ($ctx.Request.HttpMethod -eq "GET" -and ($path -eq "/version" -or $path -eq "")) {
            $tail = if (Test-Path $log) { @(Get-Content $log -Tail 3) } else { @() }
            Respond $ctx 200 @{
                version = Installed-Version; host = $env:COMPUTERNAME
                updating = (Test-Path $lock); log = $tail
            }
        } elseif ($ctx.Request.HttpMethod -eq "POST" -and $path -eq "/update") {
            $reader = New-Object IO.StreamReader($ctx.Request.InputStream)
            $body = $reader.ReadToEnd() | ConvertFrom-Json
            $version = "$($body.version)"
            if ($version -notmatch '^v?\d+\.\d+\.\d+(-[A-Za-z0-9.]+)?$') {
                Respond $ctx 400 @{ error = "bad version '$version'" }
            } elseif (Test-Path $lock) {
                Respond $ctx 409 @{ error = "an update is already running" }
            } else {
                Start-Update $version
                Respond $ctx 202 @{ status = "updating to $version"; from = Installed-Version }
                Start-Sleep -Seconds 1
                $listener.Stop()
                exit
            }
        } else {
            Respond $ctx 404 @{ error = "unknown path" }
        }
    } catch {
        try { Respond $ctx 500 @{ error = "$_" } } catch {}
    }
}
