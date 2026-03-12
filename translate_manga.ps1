param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$InputPath,

    [string]$OutputDir,

    [ValidateSet("auto", "7b", "30b")]
    [string]$ModelPreset = "7b",

    [string]$Endpoint,

    [int]$TimeoutSec = 300,

    [int]$MaxTokens = 1800,

    [int]$Limit,

    [switch]$Overwrite
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$translatorScript = Join-Path $scriptRoot "manga_translate.py"

function Test-Health {
    param([string]$HealthUrl)
    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Wait-Health {
    param(
        [string]$HealthUrl,
        [int]$Seconds
    )

    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Health -HealthUrl $HealthUrl) {
            return $true
        }
        Start-Sleep -Seconds 5
    }
    return $false
}

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

function Normalize-Endpoint {
    param([string]$Value)
    $trimmed = $Value.TrimEnd('/')
    $trimmed = $trimmed -replace '/chat/completions$', ''
    if ($trimmed -notmatch '/v1$') {
        $trimmed = "${trimmed}/v1"
    }
    return $trimmed
}

if (-not (Test-Path -LiteralPath $translatorScript)) {
    throw "Translator script not found: $translatorScript"
}

if (-not $Endpoint) {
    $candidates = @(
        "http://127.0.0.1:8001/v1",
        "http://127.0.0.1:8000/v1"
    )

    foreach ($candidate in $candidates) {
        $healthUrl = $candidate -replace '/v1$', '/health'
        if (Test-Health -HealthUrl $healthUrl) {
            $Endpoint = $candidate
            break
        }
    }
}

if (-not $Endpoint) {
    $effectivePreset = if ($ModelPreset -eq "auto") { "7b" } else { $ModelPreset }
    $port = if ($effectivePreset -eq "30b") { 8000 } else { 8001 }
    $Endpoint = "http://127.0.0.1:${port}/v1"

    Write-Host "Local Qwen endpoint is offline. Starting $effectivePreset from WSL ..." -ForegroundColor Yellow
    wsl -d Ubuntu -e bash -lc "~/workspace/start_vllm.sh $effectivePreset" | Out-Host

    if (-not (Wait-Health -HealthUrl "http://127.0.0.1:${port}/health" -Seconds $TimeoutSec)) {
        throw @"
Model startup timed out after $TimeoutSec seconds.

请检查以下事项：
1. WSL Ubuntu 是否正常运行: `wsl -d Ubuntu -l -v`
2. 启动脚本是否存在: `wsl -d Ubuntu -e bash -lc "test -f ~/workspace/start_vllm.sh && echo exists || echo missing"`
3. vLLM 启动日志: `wsl -d Ubuntu -e bash -lc "cat ~/workspace/logs/vllm-$effectivePreset.log"`
4. 端口占用情况: `wsl -d Ubuntu -e bash -lc "ss -tlnp | grep :$port"`

如果不想等待自动启动，请先手动启动服务后再运行此脚本。
"@
    }
}

$Endpoint = Normalize-Endpoint -Value $Endpoint
$python = Get-PythonCommand

Write-Host "Using endpoint: $Endpoint" -ForegroundColor Cyan

$arguments = @()
$arguments += $python.PrefixArgs
$arguments += $translatorScript
$arguments += $InputPath
$arguments += "--endpoint"
$arguments += $Endpoint
$arguments += "--timeout"
$arguments += [string]$TimeoutSec
$arguments += "--max-tokens"
$arguments += [string]$MaxTokens

if ($OutputDir) {
    $arguments += "--output-dir"
    $arguments += $OutputDir
}

if ($Limit) {
    $arguments += "--limit"
    $arguments += [string]$Limit
}

if ($Overwrite) {
    $arguments += "--overwrite"
}

& $python.Executable @arguments
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
