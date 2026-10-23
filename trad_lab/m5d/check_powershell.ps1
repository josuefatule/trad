# Safety/WhatIf tests with in-process doubles. Never call Windows firewall/process APIs.
param([Parameter(Mandatory)][string]$Plan)
$ErrorActionPreference='Stop'
$global:m5dTestMutations=0
$global:m5dTestCategory='Private'
$global:m5dTestStarted=0
function Get-NetIPAddress { param($AddressFamily) [pscustomobject]@{IPAddress='192.168.50.10';InterfaceIndex=11;InterfaceAlias='Test LAN'} }
function Get-NetConnectionProfile { param($InterfaceIndex) [pscustomobject]@{NetworkCategory=$global:m5dTestCategory} }
function Get-NetFirewallProfile { param($Name) [pscustomobject]@{Enabled=$true} }
function Get-NetFirewallRule { param($Name,$ErrorAction) return $null }
function Get-NetTCPConnection { param($State,$ErrorAction) return $null }
function New-NetFirewallRule { $global:m5dTestMutations++; throw 'REAL FIREWALL MUST NEVER BE CALLED' }
function Remove-NetFirewallRule { $global:m5dTestMutations++; throw 'REAL FIREWALL MUST NEVER BE CALLED' }
function Start-Process { $global:m5dTestStarted++; throw 'REAL PROCESS MUST NEVER BE STARTED' }
function Expect-Rejection([scriptblock]$block) {
    $rejected=$false
    try { & $block } catch { $rejected=$true }
    if (!$rejected) { throw 'Expected rejection' }
}
$launcher=Join-Path $PSScriptRoot 'Lan.ps1'
& $launcher -Plan $Plan -Action Firewall -LanIP 192.168.50.10 -ViewerIP 192.168.50.20 -Authorization 'M5-D red autorizada' -WhatIf
& $launcher -Plan $Plan -Action Start -LanIP 192.168.50.10 -ViewerIP 192.168.50.20 -Authorization 'M5-D red autorizada' -WhatIf
& $launcher -Plan $Plan -Action Close -WhatIf
Expect-Rejection { & $launcher -Plan $Plan -Action Firewall -LanIP 192.168.50.10 -ViewerIP 192.168.50.20 -WhatIf }
Expect-Rejection { & $launcher -Plan $Plan -Action Firewall -LanIP 0.0.0.0 -ViewerIP 192.168.50.20 -Authorization 'M5-D red autorizada' -WhatIf }
Expect-Rejection { & $launcher -Plan $Plan -Action Firewall -LanIP 192.168.50.10 -ViewerIP 192.168.50.10 -Authorization 'M5-D red autorizada' -WhatIf }
Expect-Rejection { & $launcher -Plan $Plan -Action Firewall -LanIP 192.168.50.10 -Authorization 'M5-D red autorizada' -WhatIf }
$global:m5dTestCategory='Public'
Expect-Rejection { & $launcher -Plan $Plan -Action Start -LanIP 192.168.50.10 -ViewerIP 192.168.50.20 -Authorization 'M5-D red autorizada' -WhatIf }
if ($global:m5dTestMutations -ne 0 -or $global:m5dTestStarted -ne 0) { throw 'A test caused side effects' }
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('m5d-state-' + [guid]::NewGuid().ToString('N') + '.json')
try {
    [IO.File]::WriteAllText($fixture,'[{"pid":1,"role":"trad"},{"pid":2,"role":"gateway"}]')
    $statePath = $fixture
    $tokens = $null; $parseErrors = $null
    $tree = [System.Management.Automation.Language.Parser]::ParseFile($launcher,[ref]$tokens,[ref]$parseErrors)
    $reader = $tree.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Read-State'},$true)
    . ([scriptblock]::Create($reader.Extent.Text))
    $rows = @(Read-State)
    if ($rows.Count -ne 2 -or @($rows | Where-Object role -eq 'gateway').Count -ne 1) { throw 'PS5/PS7 process-array enumeration regression' }
} finally {
    if (Test-Path -LiteralPath $fixture) { Remove-Item -LiteralPath $fixture }
}
Remove-Variable m5dTestMutations,m5dTestCategory,m5dTestStarted -Scope Global
Write-Output 'PASS: 9 authorization/address/profile/WhatIf/process-array checks; zero firewall mutations and zero processes started.'
