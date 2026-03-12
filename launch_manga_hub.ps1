param(
    [ValidateSet("7b", "30b")]
    [string]$ModelPreset = "7b",

    [int]$Port = 7861
)

$ErrorActionPreference = "Stop"

function Get-PythonCommand {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return @{
            Executable = $pythonCmd.Source
            PrefixArgs = @()
        }
    }

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        return @{
            Executable = $pyCmd.Source
            PrefixArgs = @("-3")
        }
    }

    throw "Python 3 was not found. Please install Python 3 first."
}

function Test-WebApp {
    param([int]$PortNumber)
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$PortNumber/api/status" -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$hubScript = Join-Path $scriptRoot "manga_hub.py"
if (-not (Test-Path -LiteralPath $hubScript)) {
    throw "Web app script not found: $hubScript"
}

if (Test-WebApp -PortNumber $Port) {
    Start-Process "http://127.0.0.1:$Port"
    exit 0
}

$python = Get-PythonCommand
$arguments = @()
$arguments += $python.PrefixArgs
$arguments += $hubScript
$arguments += "--host"
$arguments += "127.0.0.1"
$arguments += "--port"
$arguments += [string]$Port
$arguments += "--model-preset"
$arguments += $ModelPreset
$arguments += "--auto-start-model"
$arguments += "--open-browser"

Start-Process -FilePath $python.Executable -ArgumentList $arguments -WorkingDirectory $scriptRoot | Out-Null
