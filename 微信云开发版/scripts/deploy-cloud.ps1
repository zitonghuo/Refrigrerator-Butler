param([string]$CliPath = 'C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat')
$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $workspaceRoot
if (-not (Test-Path -LiteralPath $CliPath)) { throw '未找到微信开发者工具 CLI，请用 -CliPath 指定。' }
$environmentId = & node -p "require('./miniprogram/config').cloudEnv"
if (-not $environmentId -or $environmentId -notmatch '^[a-zA-Z0-9][a-zA-Z0-9-]{4,100}$') { throw '请先运行 configure-cloud.ps1 配置真实环境 ID。' }
& npm test
if ($LASTEXITCODE -ne 0) { throw '自动检查失败，停止部署。' }
$deployOutput = & $CliPath cloud functions deploy --env $environmentId --names fridgeApi --project $workspaceRoot --remote-npm-install 2>&1
$deployExit = $LASTEXITCODE
$deployOutput | Write-Output
if ($deployExit -ne 0 -or ($deployOutput -join "`n") -match '\[error\]|×|部署失败') { throw '云函数部署未成功，请根据上方错误处理后重试。' }
Write-Host '部署命令已返回。请在云开发控制台确认 fridgeApi 状态为部署成功，随后进行真实登录与双账号测试。'
Write-Host '此脚本不购买套餐，不提交微信审核，也不会发布小程序。'
