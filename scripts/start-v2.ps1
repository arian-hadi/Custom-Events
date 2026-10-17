<#
Start the isolated local V2 stack. No host Python or Node installation required.
Default: live development. Use -Mode preview for the built frontend.
Existing environment values and persistent database/media volumes are preserved.
#>
[CmdletBinding()]
param(
    [ValidateSet('dev', 'preview')]
    [string]$Mode = 'dev',
    [switch]$NoBuild,
    [switch]$PrepareOnly
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentPath = Join-Path $projectRoot '.env.v2'

function New-LocalSecret {
    $secretBytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($secretBytes) } finally { $generator.Dispose() }
    return ([BitConverter]::ToString($secretBytes)).Replace('-', '').ToLowerInvariant()
}

function Invoke-V2Compose {
    param([string[]]$Arguments)
    & docker @script:composeArguments @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Compose could not complete the operation. Review the message above; your data volumes have been preserved.'
    }
}

Push-Location $projectRoot
try {
    if (!(Test-Path -LiteralPath $environmentPath)) {
        $template = [IO.File]::ReadAllText((Join-Path $projectRoot '.env.v2.example'))
        $template = $template.Replace('replace-with-a-long-random-local-secret', (New-LocalSecret))
        $template = $template.Replace('replace-with-a-random-local-database-password', (New-LocalSecret))
        # CreateNew prevents accidentally replacing settings from another process.
        $stream = [IO.File]::Open($environmentPath, [IO.FileMode]::CreateNew)
        try {
            $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes($template)
            $stream.Write($bytes, 0, $bytes.Length)
        } finally { $stream.Dispose() }
        Write-Host 'Created .env.v2 with random local secrets. Optional integrations remain disabled.'
    } else {
        Write-Host 'Using existing .env.v2 without changing its values.'
    }
    $null = New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot '.local-v2/secrets')
    if ($PrepareOnly) { return }

    if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Install Docker Desktop, enable its Linux engine, then run this script again.'
    }
    $engine = & docker version --format '{{.Server.Os}}'
    if ($LASTEXITCODE -ne 0 -or ($engine -join '').Trim() -ne 'linux') {
        throw 'Start Docker Desktop and wait for its Linux engine to be ready, then run this script again.'
    }
    $script:composeArguments = @('compose', '--env-file', '.env.v2', '-f', 'compose.v2.yml')
    if ($Mode -eq 'dev') { $script:composeArguments += @('-f', 'compose.v2.dev.yml') }
    Invoke-V2Compose -Arguments @('config', '--quiet')
    if (!$NoBuild) { Invoke-V2Compose -Arguments @('build') }
    # Stop code services before running migrations. Keep PostgreSQL and uploads.
    Invoke-V2Compose -Arguments @('stop', 'gateway', 'frontend', 'backend', 'jobs-email', 'jobs-admin-email', 'jobs-amazon', 'jobs-league')
    Invoke-V2Compose -Arguments @('up', '-d', '--wait', '--wait-timeout', '300')
    Invoke-V2Compose -Arguments @('ps', '-a')

    $sitePort = '8082'
    $mailPort = '8026'
    $mailHost = 'mailpit'
    foreach ($line in [IO.File]::ReadAllLines($environmentPath)) {
        if ($line -match '^\s*V2_PORT\s*=\s*(\d+)\s*$') { $sitePort = $Matches[1] }
        if ($line -match '^\s*MAILPIT_PORT\s*=\s*(\d+)\s*$') { $mailPort = $Matches[1] }
        if ($line -match '^\s*EMAIL_HOST\s*=\s*(.+?)\s*$') { $mailHost = $Matches[1].Trim('"').Trim("'") }
    }
    if ($env:EMAIL_HOST) { $mailHost = $env:EMAIL_HOST }
    Write-Host "V2 $Mode is running: http://localhost:$sitePort"
    Write-Host "Administration: http://localhost:$sitePort/admin/"
    if ($mailHost -eq 'mailpit') {
        Write-Host "Captured email: http://localhost:$mailPort (no external inbox delivery)"
    } else {
        Write-Host "Email delivery: configured SMTP server ($mailHost); new messages are not captured in Mailpit."
    }
    Write-Host 'See docs/VERSION_2_DOCKER.md for admin creation, migrations, logs and stopping.'
} finally {
    Pop-Location
}
