param([switch]$SkipBuild, [switch]$Critic, [int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
    if (!(Test-Path -LiteralPath $python)) { throw 'Create .venv and install .[dev] first; see docs/cqa-phase3-deployment.md' }
    if (!$SkipBuild) {
        & npm --prefix frontend ci
        if ($LASTEXITCODE) { throw 'npm ci failed' }
        & npm --prefix frontend run build
        if ($LASTEXITCODE) { throw 'React build failed' }
    }
    if (!$env:DATABASE_URL) { $env:DATABASE_URL = 'sqlite:///.runtime/cqa-demo.db' }
    $env:LLM_PROVIDER = 'ollama'
    if (!$env:LLM_BASE_URL) { $env:LLM_BASE_URL = 'http://127.0.0.1:11434' }
    if (!$env:LLM_MODEL) { $env:LLM_MODEL = 'qwen3:4b' }
    if (!$env:LLM_CONTEXT_SIZE) { $env:LLM_CONTEXT_SIZE = '16384' }
    if (!$env:LLM_OUTPUT_LIMIT) { $env:LLM_OUTPUT_LIMIT = '4096' }
    if (!$env:LLM_TIMEOUT) { $env:LLM_TIMEOUT = '600' }
    if (!$env:CQA_JOB_TIMEOUT) { $env:CQA_JOB_TIMEOUT = '1250' }
    $env:LLM_CONCURRENCY = '1'
    $env:CQA_WORKERS = '1'
    $env:CQA_ENABLE_CRITIC = if ($Critic) { 'true' } else { 'false' }
    & $python -m cqa doctor
    if ($LASTEXITCODE) { throw 'Preflight failed: check build, disk and local Ollama/model. No model is downloaded automatically.' }
    Write-Host "Demo: http://127.0.0.1:$Port ; Critic=$env:CQA_ENABLE_CRITIC ; persistent SQLite configured"
    & $python -m cqa serve --port $Port
} finally { Pop-Location }
