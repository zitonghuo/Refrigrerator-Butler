$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:FRIDGE_DISABLE_LOCAL_VISION = '1'
$env:PYTHONUTF8 = '1'
$env:HOST = '127.0.0.1'
$env:PORT = '8765'
$env:FRIDGE_DB = Join-Path $PSScriptRoot 'data\fridge.db'
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) {
    & $pythonCommand.Source (Join-Path $PSScriptRoot 'server\app.py')
} else {
    $portablePython = Join-Path (Split-Path $PSScriptRoot -Parent) '冰箱管家便携版\冰箱管家便携版\runtime\python\python.exe'
    if (-not (Test-Path -LiteralPath $portablePython)) { throw '请安装 Python 3.10 或更高版本，然后重新启动。' }
    & $portablePython (Join-Path $PSScriptRoot 'server\app.py')
}
if ($LASTEXITCODE -ne 0) { throw '后端启动失败；如果 8765 端口被占用，请先关闭其他冰箱管家服务。' }
