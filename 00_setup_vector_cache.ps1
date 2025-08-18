# 00_setup_vector_cache.ps1
param(
  [string]$Repo = "$PWD"
)

$ErrorActionPreference = "Stop"
Write-Host "[setup] Repo: $Repo"

docker version | Out-Null

$req = Join-Path $Repo "orchestrator\requirements.txt"
$content = Get-Content $req -Raw
if ($content -notmatch "qdrant-client") { Add-Content $req "qdrant-client==1.9.1" }
if ($content -notmatch "FlagEmbedding") { Add-Content $req "FlagEmbedding==1.2.10" }

$dc = Join-Path $Repo "docker-compose.yml"
$yaml = Get-Content $dc -Raw
if ($yaml -notmatch "^\s*qdrant:\s*$") {
  $q = @"
  qdrant:
    image: qdrant/qdrant:latest
    restart: unless-stopped
    ports:
      - "6333:6333"
    volumes:
      - ./qdrant-data:/qdrant/storage
"@
  Add-Content $dc "`n$q"
}

$yaml = Get-Content $dc -Raw
if ($yaml -notmatch "QDRANT_HOST=") {
  $yaml = $yaml -replace "(gabesearch-mcp:(?:.|\n)*?environment:\s*\n)",
    "`$1      - QDRANT_HOST=host.docker.internal`n      - QDRANT_PORT=6333`n      - WEB_CACHE_COLLECTION=web-cache`n      - WEB_CACHE_TTL_DAYS=10`n"
  Set-Content $dc $yaml -Encoding UTF8
}

docker compose down
docker compose up -d --build

Write-Host "[setup] Done. Qdrant on :6333, services rebuilt."
