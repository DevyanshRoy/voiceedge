# scripts/run_gateway.ps1
param(
    [string]$Host = "0.0.0.0",
    [int]$Port = 8765,
    [string]$Serial = "off",
    [switch]$NoMonitor
)
$argsList = @("-m", "gateway.main", "--host", $Host, "--port", $Port, "--serial", $Serial)
if ($NoMonitor) { $argsList += "--no-monitor" }
python @argsList
