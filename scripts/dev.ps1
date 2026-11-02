param([ValidateSet('web','api','worker','cleanup','test','build')][string]$Service = 'web')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$localDotnet = Join-Path (Get-Location) '.tools/dotnet/dotnet.exe'
$dotnetCommand = if (Test-Path $localDotnet) { $localDotnet } else { 'dotnet' }
if (Test-Path $localDotnet) {
    $env:DOTNET_ROOT = Split-Path $localDotnet -Parent
    $env:DOTNET_CLI_HOME = Join-Path (Get-Location) '.tools/dotnet-home'
    $env:NUGET_PACKAGES = Join-Path (Get-Location) '.tools/nuget'
}
$pythonCommand = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path $pythonCommand)) { $pythonCommand = 'python' }
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
switch ($Service) {
    web { & $dotnetCommand run --project src/AIGht.Web --urls http://localhost:5080 }
    api { & $pythonCommand -m uvicorn aight_api.main:app --app-dir src --host 127.0.0.1 --port 8000 --no-access-log }
    worker { & $pythonCommand scripts/run_worker.py }
    cleanup { & $pythonCommand -m aight_api.maintenance }
    test { & $pythonCommand -m pytest }
    build { & $dotnetCommand build src/AIGht.Web/AIGht.Web.csproj }
}
exit $LASTEXITCODE
