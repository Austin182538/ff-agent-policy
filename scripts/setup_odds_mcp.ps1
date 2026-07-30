<#
.SYNOPSIS
    One-time setup for the Odds API MCP server used by .cursor/mcp.json.

.DESCRIPTION
    Node.js could not be installed automatically in this environment (the
    winget install requires an interactive UAC prompt). Run this script
    AFTER installing Node.js 18+ yourself (https://nodejs.org, or
    `winget install OpenJS.NodeJS.LTS` and approve the prompt).

    It clones the community "odds-api-mcp-server" project (wraps
    https://the-odds-api.com v4) into tools/, installs its dependencies,
    and builds it. .cursor/mcp.json already points at the resulting
    tools/odds-api-mcp-server/dist/index.js.

    After running this script, edit .cursor/mcp.json and replace
    REPLACE_WITH_YOUR_ODDS_API_KEY with your real key from
    https://the-odds-api.com, then reload Cursor's MCP servers.
#>

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$toolsDir = Join-Path $repoRoot "tools"
$targetDir = Join-Path $toolsDir "odds-api-mcp-server"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Error "Node.js not found on PATH. Install it first (https://nodejs.org or 'winget install OpenJS.NodeJS.LTS'), then re-run this script."
    exit 1
}

New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

if (-not (Test-Path $targetDir)) {
    git clone https://github.com/acraw4d/odds-api-mcp-server.git $targetDir
} else {
    Write-Host "$targetDir already exists, skipping clone."
}

Push-Location $targetDir
try {
    npm install
    npm run build
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Done. Now edit .cursor/mcp.json and set your real ODDS_API_KEY, then reload MCP servers in Cursor."
