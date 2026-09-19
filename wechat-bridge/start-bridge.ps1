param(
    [switch]$RetryFailed
)

$ErrorActionPreference = 'Stop'
$python = Join-Path $env:USERPROFILE 'wxauto-test\Scripts\python.exe'
$script = Join-Path $PSScriptRoot 'bridge.py'

if (-not (Test-Path -LiteralPath $python)) {
    throw "找不到 wxauto4 环境：$python"
}

$arguments = @(
    $script,
    '--chat', '微信接入测试',
    '--worker-url', 'https://kexu-campus-mvp.richeng.workers.dev',
    '--poll',
    '--prompt-access-token'
)
if ($RetryFailed) { $arguments += '--retry-failed' }
& $python @arguments
exit $LASTEXITCODE
