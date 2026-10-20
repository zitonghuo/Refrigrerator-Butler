param([Parameter(Mandatory=$true)][string]$EnvironmentId)
$ErrorActionPreference = 'Stop'
if ($EnvironmentId -notmatch '^[a-zA-Z0-9][a-zA-Z0-9-]{4,100}$') { throw '环境 ID 格式不正确，请从云开发控制台复制。' }
$workspaceRoot = Split-Path $PSScriptRoot -Parent
$configPath = Join-Path $workspaceRoot 'miniprogram\config.js'
$content = Get-Content -LiteralPath $configPath -Raw -Encoding utf8
$content = $content -replace "cloudEnv: '[^']*'", "cloudEnv: '$EnvironmentId'"
[System.IO.File]::WriteAllText($configPath, $content, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "已配置云环境：$EnvironmentId"
Write-Host '下一步：按 docs/云开发部署.md 创建数据库集合，部署 fridgeApi，然后在工具中编译。'
