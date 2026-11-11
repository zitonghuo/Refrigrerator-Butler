param(
    [string]$Python = 'python',
    [string]$ListenAddress = '127.0.0.1',
    [int]$Port = 8770
)
$ErrorActionPreference = 'Stop'
$weights = Join-Path $PSScriptRoot 'weights/fruits_vegetables_yolov8m_seg_expanded_v4.pt'
if (-not (Test-Path -LiteralPath $weights)) {
    throw 'Download fruits_vegetables_yolov8m_seg_expanded_v4.pt from the models-v1 release into vision/weights first.'
}
$env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
$env:OMP_NUM_THREADS = '4'
$env:MKL_NUM_THREADS = '4'
& $Python -m food_recognition.server --backend trained --produce-weights $weights --host $ListenAddress --port $Port
exit $LASTEXITCODE
