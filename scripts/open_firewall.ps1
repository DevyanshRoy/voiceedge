# scripts/open_firewall.ps1
param(
    [string]$GatewayExecutable = ""
)
New-NetFirewallRule -DisplayName "VoiceEdge signaling" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow
New-NetFirewallRule -DisplayName "VoiceEdge discovery" -Direction Inbound -Protocol UDP -LocalPort 8766 -Action Allow
if ($GatewayExecutable) {
    New-NetFirewallRule -DisplayName "VoiceEdge gateway media" -Direction Inbound `
        -Protocol UDP -Program (Resolve-Path $GatewayExecutable).Path -Action Allow
} else {
    New-NetFirewallRule -DisplayName "VoiceEdge Python media" -Direction Inbound `
        -Protocol UDP -Program (Get-Command python).Source -Action Allow
}
