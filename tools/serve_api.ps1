# Запуск RAG-API (Windows PowerShell)

if ($env:FALT_CORPUS_ROOT) { $ROOT = $env:FALT_CORPUS_ROOT } else { $ROOT = Join-Path (Split-Path $PSScriptRoot -Parent) (Split-Path $PSScriptRoot -Leaf) | Split-Path -Parent }
# tools -> course -> workspace root
$ROOT = Split-Path $ROOT -Parent
$py = Join-Path $ROOT ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$api = Join-Path $ROOT "scripts\rag_api.py"
if (-not (Test-Path $api)) { Write-Error "Корпус не найден: $api (см. CORPUS.md)"; exit 2 }
$port = 8765
if ($args.Count -gt 0) { $port = $args[0] }
Write-Host "RAG API: http://127.0.0.1:$port  (Ctrl+C — стоп)"
& $py $api --port $port