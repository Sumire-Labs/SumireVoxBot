# SumireVox Setup Script (repo-root)
# - Creates .env.common from .env.template (removes DISCORD_TOKEN lines)
# - Creates app/bot/.env.botX containing DISCORD_TOKEN only
# - Generates docker-compose.yml at repo root
# - Optionally starts containers

param(
    [int]$BotCount = 0,
    [switch]$SkipDockerCheck = $false,
    [switch]$SkipStartDocker = $false
)

$ErrorActionPreference = "Stop"

# ---------- Paths ----------
$RepoRoot = Resolve-Path $PSScriptRoot
$BotDir = Join-Path $RepoRoot "app\bot"

$EnvTemplatePath = Join-Path $RepoRoot ".env.template"
$EnvCommonPath = Join-Path $RepoRoot ".env.common"
$ComposeOutputPath = Join-Path $RepoRoot "docker-compose.yml"

# ---------- UI helpers ----------
function Write-Colored {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
}

function Write-Header {
    Write-Host ""
    Write-Colored "╔═══════════════════════════════════════╗" Cyan
    Write-Colored "║   SumireVox Setup & Installation      ║" Cyan
    Write-Colored "║          Auto Setup Script            ║" Cyan
    Write-Colored "╚═══════════════════════════════════════╝" Cyan
    Write-Host ""
}

# ---------- Validation ----------
function Assert-RepoLayout {
    if (-not (Test-Path $EnvTemplatePath)) {
        throw ".env.template not found at: $EnvTemplatePath"
    }
    if (-not (Test-Path $BotDir)) {
        throw "Bot directory not found at: $BotDir"
    }
    if (-not (Test-Path (Join-Path $BotDir "Dockerfile"))) {
        throw "Bot Dockerfile not found at: $(Join-Path $BotDir "Dockerfile")"
    }
}

# ---------- Docker compose command detection ----------
function Get-ComposeRunner {
    # Prefer v2: docker compose
    try {
        $null = docker compose version 2>$null
        return @{
            Mode = "v2"
            Up   = { param($cwd) Push-Location $cwd; try { docker compose up -d } finally { Pop-Location } }
            Ps   = { param($cwd) Push-Location $cwd; try { docker compose ps } finally { Pop-Location } }
        }
    } catch {}

    # Fallback v1: docker-compose
    try {
        $null = docker-compose --version 2>$null
        return @{
            Mode = "v1"
            Up   = { param($cwd) Push-Location $cwd; try { docker-compose up -d } finally { Pop-Location } }
            Ps   = { param($cwd) Push-Location $cwd; try { docker-compose ps } finally { Pop-Location } }
        }
    } catch {}

    throw "Docker Compose not found. Install Docker Desktop (Compose v2 recommended)."
}

# ---------- Env generation ----------
function Ensure-EnvCommon {
    if (Test-Path $EnvCommonPath) {
        Write-Colored "✓ .env.common already exists (will not overwrite): $EnvCommonPath" Green
        return
    }

    $lines = Get-Content -Path $EnvTemplatePath -Encoding UTF8

    # Remove lines like: DISCORD_TOKEN=...
    $filtered = $lines | Where-Object { $_ -notmatch '^\s*DISCORD_TOKEN\s*=' }

    Set-Content -Path $EnvCommonPath -Value $filtered -Encoding UTF8
    Write-Colored "✓ Created .env.common from .env.template (DISCORD_TOKEN removed): $EnvCommonPath" Green
    Write-Colored "  NOTE: Update POSTGRES_PASSWORD in .env.common for non-dev usage." Yellow
}

function Write-BotEnv {
    param([int]$Index, [string]$Token)

    $envPath = Join-Path $BotDir ".env.bot$Index"
    Set-Content -Path $envPath -Value @("DISCORD_TOKEN=$Token") -Encoding UTF8
    Write-Colored "✓ Wrote $envPath" Green
}

# ---------- docker-compose.yml generation ----------
function New-DockerComposeYaml {
    param([int]$BotCount)

    $sb = New-Object System.Text.StringBuilder

    [void]$sb.AppendLine('version: "3.8"')
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("x-bot-template: &bot-template")
    [void]$sb.AppendLine("  build:")
    [void]$sb.AppendLine("    context: ./app/bot")
    [void]$sb.AppendLine("  volumes:")
    [void]$sb.AppendLine("    - ./app/bot:/app")
    [void]$sb.AppendLine("  depends_on:")
    [void]$sb.AppendLine("    - db")
    [void]$sb.AppendLine("    - voicevox_engine")
    [void]$sb.AppendLine("  networks:")
    [void]$sb.AppendLine("    - sumire_vox_network")
    [void]$sb.AppendLine("  restart: unless-stopped")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("services:")

    for ($i = 1; $i -le $BotCount; $i++) {
        [void]$sb.AppendLine("  bot$($i):")
        [void]$sb.AppendLine("    <<: *bot-template")
        [void]$sb.AppendLine("    container_name: sumire_vox_bot_$($i)")
        [void]$sb.AppendLine("    env_file:")
        [void]$sb.AppendLine("      - ./.env.common")
        [void]$sb.AppendLine("      - ./app/bot/.env.bot$($i)")
        [void]$sb.AppendLine("")
    }

    [void]$sb.AppendLine("  voicevox_engine:")
    [void]$sb.AppendLine("    image: voicevox/voicevox_engine:cpu-ubuntu20.04-latest")
    [void]$sb.AppendLine("    container_name: voicevox_engine")
    [void]$sb.AppendLine("    ports:")
    [void]$sb.AppendLine('      - "50021:50021"')
    [void]$sb.AppendLine("    restart: unless-stopped")
    [void]$sb.AppendLine("    volumes:")
    [void]$sb.AppendLine("      - ./app/bot/voicevox_config:/root/.local/share/voicevox_engine")
    [void]$sb.AppendLine("    networks:")
    [void]$sb.AppendLine("      - sumire_vox_network")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("  db:")
    [void]$sb.AppendLine("    image: postgres:15")
    [void]$sb.AppendLine("    container_name: sumire_vox_db")
    [void]$sb.AppendLine("    restart: always")
    [void]$sb.AppendLine("    env_file:")
    [void]$sb.AppendLine("      - ./.env.common")
    [void]$sb.AppendLine("    ports:")
    [void]$sb.AppendLine('      - "5432:5432"')
    [void]$sb.AppendLine("    volumes:")
    [void]$sb.AppendLine("      - ./app/bot/postgres_data:/var/lib/postgresql/data")
    [void]$sb.AppendLine("    networks:")
    [void]$sb.AppendLine("      - sumire_vox_network")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("networks:")
    [void]$sb.AppendLine("  sumire_vox_network:")
    [void]$sb.AppendLine("    driver: bridge")

    return $sb.ToString()
}

# ---------- Main ----------
Write-Header
Assert-RepoLayout

Write-Colored "[Step 1/5] Preparing .env.common..." Yellow
Ensure-EnvCommon
Write-Host ""

Write-Colored "[Step 2/5] Checking Docker / Compose..." Yellow
$compose = Get-ComposeRunner
Write-Colored "✓ Compose mode: $($compose.Mode)" Green
Write-Host ""

Write-Colored "[Step 3/5] Configuring bot instances..." Yellow
if ($BotCount -le 0) {
    $BotCountInput = Read-Host "How many bot instances do you want to create? (default: 1)"
    $BotCount = if ($BotCountInput -eq "") { 1 } else { [int]$BotCountInput }
    if ($BotCount -le 0) { $BotCount = 1 }
}
Write-Colored "✓ Bot instances: $BotCount" Green
Write-Host ""

Write-Colored "[Step 4/5] Creating app/bot/.env.botX (DISCORD_TOKEN only)..." Yellow
for ($i = 1; $i -le $BotCount; $i++) {
    Write-Colored "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" Cyan
    $token = Read-Host "Enter Discord Token for bot instance $i"
    Write-Colored "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" Cyan

    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "Discord Token cannot be empty."
    }

    Write-BotEnv -Index $i -Token $token
}
Write-Host ""

Write-Colored "[Step 5/5] Generating docker-compose.yml..." Yellow
$yaml = New-DockerComposeYaml -BotCount $BotCount
Set-Content -Path $ComposeOutputPath -Value $yaml -Encoding UTF8
Write-Colored "✓ Generated: $ComposeOutputPath" Green
Write-Host ""

if (-not $SkipStartDocker) {
    $resp = Read-Host "Start Docker containers now? (y/n, default: y)"
    if ($resp -ne "n") {
        & $compose.Up $RepoRoot
        & $compose.Ps $RepoRoot
        Write-Colored "✓ Containers started." Green
    } else {
        Write-Colored "Skipped starting containers." Yellow
    }
} else {
    Write-Colored "Skipped starting containers." Yellow
}