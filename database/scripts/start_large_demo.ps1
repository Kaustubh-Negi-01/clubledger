# Start only the isolated reviewer dataset. The usual preview on 8010 is untouched.
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$demoDatabase = Join-Path $repoRoot 'database/runtime/large-demo/clubledger-large-demo.db'
if (-not (Test-Path -LiteralPath $demoDatabase)) {
    throw 'Create the dataset first: .venv\Scripts\python.exe database/scripts/create_large_demo.py'
}
Set-Location -LiteralPath $repoRoot
$env:PYTHONPATH = Join-Path $repoRoot 'backend'
$env:CLUBLEDGER_ENV = 'dev'
# PowerShell can remove empty environment values, so remove the cloud URL after
# dotenv loads too, in the Python launcher below.
$env:CLUBLEDGER_DB_PATH = $demoDatabase
$env:CLUBLEDGER_RECEIPTS_DIR = Join-Path $repoRoot 'database/runtime/large-demo/receipts'
$env:CLUBLEDGER_SIM_SECRET = 'isolated-local-synthetic-demo-only'
& '.venv\Scripts\python.exe' -c "import os; from clubledger.config import get_config; os.environ['CLUBLEDGER_DATABASE_URL']=''; from clubledger.cli import handle_start; handle_start('127.0.0.1',8011)"
