# scripts/run_client.ps1
param(
    [string]$Server = "127.0.0.1:8765",
    [string]$Name = $env:COMPUTERNAME,
    [string]$Room = "lab"
)
python -m client.webrtc_client --cli --server $Server --name $Name --room $Room
