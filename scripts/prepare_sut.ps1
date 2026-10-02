$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoPath '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = 'python' }
& $pythonPath -X utf8 (Join-Path $PSScriptRoot 'prepare_e2e.py')
if ($LASTEXITCODE -ne 0) { throw 'Pinned E2E preparation failed; existing files were not reset.' }
