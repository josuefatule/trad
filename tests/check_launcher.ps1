# Exercise production functions with process/firewall doubles. No real mutation.
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$sourcePath = Join-Path $ProjectRoot 'Start-TRAD.ps1'
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($sourcePath,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($definition in $ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$false)) {
    Invoke-Expression $definition.Extent.Text
}
$script:passed = 0
function Assert($Condition, $Message) { if (-not $Condition) { throw $Message }; $script:passed++ }
function Reject($Block, $Message) { $rejected=$false; try { & $Block } catch { $rejected=$true }; Assert $rejected $Message }
Assert (Test-PrivateIP '10.0.0.88') 'Private IPv4 rejected'
Assert (Test-PrivateIP '172.16.5.2') '172 private rejected'
Assert (Test-PrivateIP '192.168.1.4') '192 private rejected'
foreach ($bad in @('0.0.0.0','127.0.0.1','8.8.8.8','10.1','::1','10.0.0.88;whoami')) { Assert (-not (Test-PrivateIP $bad)) ('Unsafe IP accepted: '+$bad) }
$LocalIP='10.0.0.88';$OverlayIP='10.0.0.105'
function Get-LocalNetworks { [pscustomobject]@{ip='10.0.0.88';profile=$script:profile;interface='Wi-Fi';index=11} }
function Get-NetFirewallProfile { [pscustomobject]@{Enabled=$true} }
$script:profile='Public'
Assert ((Confirm-LanSelection).ip -eq $LocalIP) 'Public profile rejected'
$script:profile='Private'
Assert ((Confirm-LanSelection).ip -eq $LocalIP) 'Private selection rejected'
$OverlayIP=$LocalIP;Reject { Confirm-LanSelection } 'Same computer accepted'
$OverlayIP='';Assert ((Confirm-LanSelection).ip -eq $LocalIP) 'Optional receiver IP required'
$OverlayIP='10.0.0.105';$LocalIP='10.0.0.99';Reject { Confirm-LanSelection } 'Unassigned local IP accepted';$LocalIP='10.0.0.88'
$created=[DateTime]::UtcNow
$entry=[pscustomobject]@{pid=42;created_ticks=$created.ToUniversalTime().Ticks.ToString();role='api';run_id='abc123';owned=$true}
$script:process=[pscustomobject]@{CreationDate=$created;CommandLine='C:\live-captions\.venv\Scripts\python.exe -B -m app.service_host --role api --run-id abc123 --pid-file C:\live-captions\.runtime\x';ProcessId=42}
function Get-ProcessRecord { param($ProcessId) return $script:process }
Assert ([bool](Get-OwnedProcess $entry)) 'Own process not recognized'
$entry.created_ticks='0';Assert (-not (Get-OwnedProcess $entry)) 'Reused PID accepted';$entry.created_ticks=$created.ToUniversalTime().Ticks.ToString()
$script:process.CommandLine='python other_app.py';Assert (-not (Get-OwnedProcess $entry)) 'Foreign process accepted'
function Get-Listeners { param($Port) @([pscustomobject]@{LocalAddress='127.0.0.1';OwningProcess=42}) }
function Start-Owned { throw 'Unexpected process creation' }
$script:LaunchState=[pscustomobject]@{services=@()}
Reject { Use-OrStart 'api' 8010 'python' 'app\.service_host' 'unused' } 'Occupied foreign port accepted'
function Get-OperatorState { [pscustomobject]@{session_open=$true;can_start=$false} }
Reject { Confirm-Idle } 'Active session may be stopped'
function Get-OperatorState { [pscustomobject]@{session_open=$false;can_start=$true} }
Confirm-Idle;Assert $true 'Idle rejected'
function Get-OperatorState { [pscustomobject]@{session_open=$false;can_start=$false;state='error'} }
Confirm-CaptureClosed;Assert $true 'ASR recovery should allow a closed incomplete session'
function Get-OperatorState { [pscustomobject]@{session_open=$true;can_start=$false;state='live'} }
Reject { Confirm-CaptureClosed } 'ASR recovery interrupted active capture'
$RuleName='TRAD-MVP-Overlay';$FirewallPath='unused';$script:ruleCreated=0
function Get-NetFirewallRule { @() }
function Save-Json { param($Path,$Value) $script:savedRule=$Value }
function New-NetFirewallRule {
    param($Name,$DisplayName,$Direction,$Action,$Enabled,$Profile,$Protocol,$LocalPort,$LocalAddress,$RemoteAddress,$InterfaceAlias,$EdgeTraversalPolicy)
    Assert ($LocalAddress -eq '10.0.0.88' -and $RemoteAddress -eq 'Any') 'Overlay should allow any receiver'
    Assert ($LocalPort -eq 3000 -and $Protocol -eq 'TCP' -and $Profile -eq 'Any') 'Overlay must work on Public and Private'
    Assert ($Direction -eq 'Inbound' -and $Action -eq 'Allow' -and $EdgeTraversalPolicy -eq 'Block') 'Firewall direction changed'
    $script:ruleCreated++
}
Add-OverlayFirewall
Assert ($script:ruleCreated -eq 1 -and $script:savedRule.overlay_pc_ip -eq '10.0.0.105') 'Scoped firewall not recorded'
$script:profile='Public';$OverlayIP='';Add-OverlayFirewall
Assert ($script:ruleCreated -eq 2 -and $script:savedRule.remote_address -eq 'Any') 'Public open overlay failed'
Write-Host "PASS: $script:passed controles de PowerShell, sin procesos ni reglas reales."
