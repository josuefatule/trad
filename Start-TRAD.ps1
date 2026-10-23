#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Start','Status','Test','Stop','RestartASR','Firewall','CloseFirewall')][string]$Action = 'Start',
    [string]$OverlayIP,
    [string]$LocalIP,
    [switch]$LocalOnly,
    [switch]$NoBrowser,
    [switch]$SkipPrompts,
    [ValidateRange(15,600)][int]$TimeoutSeconds = 180
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$Runtime = Join-Path $ProjectRoot '.runtime\launcher'
$StatePath = Join-Path $Runtime 'state.json'
$NetworkPath = Join-Path $Runtime 'network.json'
$FirewallPath = Join-Path $Runtime 'firewall.json'
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$AsrPython = Join-Path $ProjectRoot '.venv-wlk\Scripts\python.exe'
$ApiBase = 'http://localhost:8010'
$ApiCheckBase = 'http://127.0.0.1:8010'
$RuleName = 'TRAD-MVP-Overlay'

function Save-Json($Path, $Value) {
    $temporary = $Path + '.tmp'
    $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}
function Read-Json($Path) {
    if (Test-Path -LiteralPath $Path) { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
    return $null
}
function Test-PrivateIP([string]$Value) {
    $address = $null
    if (-not [Net.IPAddress]::TryParse($Value, [ref]$address) -or $address.AddressFamily -ne 'InterNetwork' -or $address.ToString() -ne $Value) { return $false }
    $bytes = $address.GetAddressBytes()
    return ($bytes[0] -eq 10 -or ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or ($bytes[0] -eq 192 -and $bytes[1] -eq 168))
}
function Get-LocalNetworks {
    foreach ($address in @(Get-NetIPAddress -AddressFamily IPv4)) {
        if (Test-PrivateIP $address.IPAddress) {
            $profile = @(Get-NetConnectionProfile -InterfaceIndex $address.InterfaceIndex -ErrorAction SilentlyContinue)
            [pscustomobject]@{ ip=$address.IPAddress; interface=$address.InterfaceAlias; index=$address.InterfaceIndex; profile= $(if ($profile.Count) { [string]$profile[0].NetworkCategory } else { 'Unknown' }) }
        }
    }
}
function Confirm-LanSelection {
    if (-not (Test-PrivateIP $LocalIP)) { throw 'Selecciona una IPv4 de esta PC de la lista mostrada.' }
    if ($OverlayIP -and (-not (Test-PrivateIP $OverlayIP) -or $LocalIP -eq $OverlayIP)) { throw 'La IP opcional de la PC overlay debe ser una IPv4 de otro equipo.' }
    $matches = @(Get-LocalNetworks | Where-Object { $_.ip -eq $LocalIP })
    if ($matches.Count -ne 1) { throw 'La IP local seleccionada no esta asignada a esta PC.' }
    return $matches[0]
}
function Test-Administrator {
    return ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Invoke-FirewallAction([string]$Operation) {
    $parameters = @('-NoProfile','-File', ('"' + $PSCommandPath + '"'), '-Action', $Operation)
    if ($Operation -eq 'Firewall') {
        $parameters += @('-LocalIP',$LocalIP)
        if ($OverlayIP) { $parameters += @('-OverlayIP',$OverlayIP) }
    }
    $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $parameters -Verb RunAs -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw 'Windows no pudo aplicar la regla del overlay. Consulta .runtime\launcher\firewall-error.txt.' }
}
function Add-OverlayFirewall {
    $selected = Confirm-LanSelection
    $existing = @(Get-NetFirewallRule -Name $RuleName -ErrorAction SilentlyContinue)
    if ($existing.Count) {
        $saved = Read-Json $FirewallPath
        $filter = $existing | Get-NetFirewallAddressFilter
        $port = $existing | Get-NetFirewallPortFilter
        $iface = $existing | Get-NetFirewallInterfaceFilter
        $expectedRemote = if ($saved.remote_address) { $saved.remote_address } else { $saved.overlay_pc_ip }
        if (-not $saved -or $saved.local_ip -ne $LocalIP -or
            $existing.Count -ne 1 -or [string]$existing[0].Direction -ne 'Inbound' -or
            [string]$existing[0].Action -ne 'Allow' -or [string]$existing[0].Enabled -ne 'True' -or
            [string]$filter.LocalAddress -ne $LocalIP -or [string]$filter.RemoteAddress -ne $expectedRemote -or
            [string]$port.LocalPort -ne '3000' -or [string]$port.Protocol -ne 'TCP' -or [string]$iface.InterfaceAlias -ne $selected.interface) {
            throw 'Ya existe una regla con este nombre y no coincide con esta configuracion. No se modifico.'
        }
        $existing | Set-NetFirewallRule -Profile Any -EdgeTraversalPolicy Block | Out-Null
        $filter | Set-NetFirewallAddressFilter -RemoteAddress Any | Out-Null
    } else {
        New-NetFirewallRule -Name $RuleName -DisplayName 'TRAD MVP - overlay abierto' -Direction Inbound -Action Allow -Enabled True -Profile Any -Protocol TCP -LocalPort 3000 -LocalAddress $LocalIP -RemoteAddress Any -InterfaceAlias $selected.interface -EdgeTraversalPolicy Block | Out-Null
    }
    Save-Json $FirewallPath @{name=$RuleName;local_ip=$LocalIP;overlay_pc_ip=$OverlayIP;interface=$selected.interface;remote_address='Any';overlay_access='any'}
}
function Remove-OverlayFirewall {
    $saved = Read-Json $FirewallPath
    if (-not $saved) { return }
    $existing = @(Get-NetFirewallRule -Name $RuleName -ErrorAction SilentlyContinue)
    if ($existing.Count) {
        $filter = $existing | Get-NetFirewallAddressFilter
        $port = $existing | Get-NetFirewallPortFilter
        $expectedRemote = if ($saved.remote_address) { $saved.remote_address } else { $saved.overlay_pc_ip }
        if ([string]$filter.LocalAddress -ne $saved.local_ip -or [string]$filter.RemoteAddress -ne $expectedRemote -or [string]$port.LocalPort -ne '3000') { throw 'La regla cambio fuera de TRAD; no se retiro automaticamente.' }
        $existing | Remove-NetFirewallRule
    }
    Remove-Item -LiteralPath $FirewallPath
}
function Get-Listeners([int]$Port) {
    return @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}
function Get-ProcessRecord([int]$ProcessId) {
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
}
function Get-Stamp($Process) { return $Process.CreationDate.ToUniversalTime().Ticks.ToString() }
function Test-ProjectProcess($Process, [string]$Executable) {
    if ($Process.CommandLine.Contains($ProjectRoot)) { return $true }
    # Windows venv shims launch the base Python interpreter as a child.
    $parent = Get-ProcessRecord ([int]$Process.ParentProcessId)
    return ($null -ne $parent -and $parent.ExecutablePath -eq $Executable -and
        $parent.CommandLine.Contains($ProjectRoot) -and $parent.CreationDate -le $Process.CreationDate)
}
function Get-OwnedProcess($Entry) {
    $process = Get-ProcessRecord ([int]$Entry.pid)
    if ($process -and (Get-Stamp $process) -eq [string]$Entry.created_ticks -and
        $process.CommandLine -match ('app\.service_host\s+--role\s+' + [regex]::Escape($Entry.role) + '\s+--run-id\s+' + [regex]::Escape($Entry.run_id) + '(\s|$)') -and
        $process.CommandLine.Contains($ProjectRoot)) { return $process }
    return $null
}
function Get-OperatorState {
    $bootstrap = Invoke-RestMethod "$ApiCheckBase/api/operator/bootstrap" -TimeoutSec 4
    return Invoke-RestMethod "$ApiCheckBase/api/operator/status" -Headers @{'X-Operator-Token'=$bootstrap.control_token} -TimeoutSec 4
}
function Confirm-Idle {
    if (@(Get-Listeners 8010).Count) {
        $status = Get-OperatorState
        if ($status.session_open -or -not $status.can_start) { throw 'Deten primero la sesion desde Operator. No se interrumpio el audio ni una traduccion.' }
    }
}
function Confirm-CaptureClosed {
    if (@(Get-Listeners 8010).Count) {
        $status = Get-OperatorState
        if ($status.session_open -or $status.state -in @('connecting','live','draining')) {
            throw 'Deten primero la captura desde Operator. No se reinicio el reconocedor.'
        }
    }
}
function Save-State { Save-Json $StatePath $script:LaunchState }
function Wait-Healthy([string]$Url, [string]$Role) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $health = Invoke-RestMethod $Url -TimeoutSec 3
            if ($health.status -eq 'ok' -and ($Role -ne 'asr' -or ($health.ready -and $health.backend -eq 'faster-whisper'))) { return $health }
        } catch { }
        $own = @($script:LaunchState.services | Where-Object { $_.role -eq $Role -and $_.owned })
        if ($own.Count -and -not (Get-OwnedProcess $own[0])) { throw "El servicio $Role termino. Revisa sus logs en $Runtime." }
        Start-Sleep -Milliseconds 500
    }
    throw "El servicio $Role no estuvo listo dentro de $TimeoutSeconds segundos. Se conservaron los logs."
}
function Start-Owned([string]$Role, [string]$Executable, [string[]]$Extra = @()) {
    $id = [guid]::NewGuid().ToString('N')
    $pidFile = Join-Path $Runtime "$Role-$id.pid.json"
    $stopFile = Join-Path $Runtime "$Role-$id.stop"
    $arguments = @('-B','-m','app.service_host','--role',$Role,'--run-id',$id,'--pid-file',$pidFile,'--stop-file',$stopFile) + $Extra
    $specFile = Join-Path $Runtime "$Role-$id.launch.json"
    Save-Json $specFile @{executable=$Executable;arguments=$arguments;stdout=(Join-Path $Runtime "$Role-$id.out.log");stderr=(Join-Path $Runtime "$Role-$id.err.log")}
    $started = & $Python -B (Join-Path $ProjectRoot 'tools\start_trad_service.py') $specFile
    if ($LASTEXITCODE -ne 0) { throw "No se pudo iniciar $Role. Revisa sus logs." }
    $process = Get-Process -Id (($started | ConvertFrom-Json).pid) -ErrorAction Stop
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    while (-not (Test-Path -LiteralPath $pidFile) -and [DateTime]::UtcNow -lt $deadline) {
        if ($process.HasExited) { throw "No pudo iniciar $Role. Revisa sus logs." }
        Start-Sleep -Milliseconds 100
    }
    $identity = Read-Json $pidFile
    if (-not $identity -or $identity.run_id -ne $id) { throw "No se pudo confirmar la identidad de $Role." }
    $actual = Get-ProcessRecord ([int]$identity.pid)
    if (-not $actual) { throw "El proceso $Role termino durante el inicio." }
    $entry = [pscustomobject]@{role=$Role;pid=[int]$identity.pid;created_ticks=(Get-Stamp $actual);run_id=$id;stop_file=$stopFile;owned=$true}
    $script:LaunchState.services = @($script:LaunchState.services) + $entry
    Save-State
    return $entry
}
function Use-OrStart([string]$Role, [int]$Port, [string]$Executable, [string]$Expected, [string]$Url) {
    $listeners = @(Get-Listeners $Port)
    if ($listeners.Count) {
        if (@($listeners | Where-Object { $_.LocalAddress -notin @('127.0.0.1','::1') }).Count) { throw "El puerto $Port esta expuesto fuera de loopback. No se reutilizo." }
        $ids = @($listeners.OwningProcess | Select-Object -Unique)
        $process = Get-ProcessRecord ([int]$ids[0])
        if ($ids.Count -ne 1 -or -not $process -or $process.CommandLine -notmatch $Expected -or -not (Test-ProjectProcess $process $Executable)) { throw "El puerto $Port pertenece a otro proceso. No se cerro ni se inicio un duplicado." }
        $prior = @($script:LaunchState.services | Where-Object { $_.role -eq $Role -and $_.owned -and $_.pid -eq $process.ProcessId -and (Get-OwnedProcess $_) })
        if (-not $prior.Count) {
            $script:LaunchState.services = @($script:LaunchState.services | Where-Object { $_.role -ne $Role }) + [pscustomobject]@{role=$Role;pid=[int]$process.ProcessId;owned=$false}
        }
        Write-Host "$Role ya estaba iniciado; se verifica sin duplicarlo."
    } else {
        $script:LaunchState.services = @($script:LaunchState.services | Where-Object { $_.role -ne $Role })
        Write-Host "Iniciando $Role..."
        Start-Owned $Role $Executable | Out-Null
    }
    $health = Wait-Healthy $Url $Role
    if ($Role -eq 'api' -and $health.launcher_version -ne 'mvp-launcher-v1') { throw 'El servidor existente usa codigo anterior. Detenlo sin sesion activa y vuelve a ejecutar el lanzador.' }
    Save-State
}
function Stop-Entries($Entries) {
    foreach ($entry in @($Entries | Sort-Object @{Expression={ if ($_.role -eq 'gateway') {0} elseif ($_.role -eq 'api') {1} else {2} }})) {
        if (-not $entry.owned -or -not (Get-OwnedProcess $entry)) { continue }
        Write-Host "Cerrando $($entry.role)..."
        if ($entry.role -eq 'asr') { Stop-Process -Id $entry.pid -ErrorAction Stop }
        else {
            Set-Content -LiteralPath $entry.stop_file -Value 'stop' -Encoding ASCII
            $deadline = [DateTime]::UtcNow.AddSeconds(15)
            while ((Get-OwnedProcess $entry) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 200 }
            if (Get-OwnedProcess $entry) { throw "$($entry.role) no confirmo el cierre. No se forzo ni se cerraron procesos ajenos." }
        }
    }
}

New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
if ($Action -in @('Firewall','CloseFirewall')) {
    try {
        if (-not (Test-Administrator)) { throw 'La regla limitada necesita permisos de administrador de Windows.' }
        if ($Action -eq 'Firewall') { Add-OverlayFirewall } else { Remove-OverlayFirewall }
        exit 0
    } catch { $_.Exception.Message | Set-Content (Join-Path $Runtime 'firewall-error.txt'); Write-Error $_; exit 1 }
}
$mutex = New-Object Threading.Mutex($false, 'Local\TRAD-MVP-Launcher')
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'Ya hay otro comando de TRAD en ejecucion. Espera a que termine.' }
    if (-not (Test-Path -LiteralPath $Python) -or -not (Test-Path -LiteralPath $AsrPython)) { throw 'Faltan .venv o .venv-wlk. No se instalaron ni cambiaron dependencias.' }
    $script:LaunchState = Read-Json $StatePath
    if (-not $script:LaunchState) { $script:LaunchState = [pscustomobject]@{version='mvp-launcher-v1';services=@()} }
    if ($Action -eq 'Status') {
        Write-Host 'Operator: http://localhost:8010/operator'
        foreach ($port in @(8000,8010,3000)) { Get-Listeners $port | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table }
        $network = Read-Json $NetworkPath
        if ($network) { Write-Host "IP de esta PC: $($network.local_ip) | PC overlay: $($network.overlay_pc_ip) | LAN: $($network.lan_enabled)" }
        exit 0
    }
    if ($Action -eq 'Test') {
        Push-Location $ProjectRoot
        try { & $Python -B tools/smoke_trad.py; if ($LASTEXITCODE -ne 0) { throw 'La prueba sencilla detecto un problema.' } } finally { Pop-Location }
        exit 0
    }
    if ($Action -eq 'RestartASR') {
        Confirm-CaptureClosed
        $asrEntries = @($script:LaunchState.services | Where-Object { $_.role -eq 'asr' })
        $running = @(Get-Listeners 8000)
        $owned = @($asrEntries | Where-Object { $_.owned -and (Get-OwnedProcess $_) })
        if ($running.Count -and (-not $owned.Count -or @($running | Where-Object { $_.OwningProcess -notin $owned.pid }).Count)) {
            throw 'El ASR actual no pertenece al lanzador. No se cerro un proceso ajeno.'
        }
        Stop-Entries $owned
        $deadline = [DateTime]::UtcNow.AddSeconds(10)
        while (@(Get-Listeners 8000).Count -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 200 }
        if (@(Get-Listeners 8000).Count) { throw 'El reconocedor anterior no libero el puerto.' }
        $script:LaunchState.services = @($script:LaunchState.services | Where-Object { $_.role -ne 'asr' })
        Save-State
        $savedPath = $env:PATH; $savedOffline = $env:HF_HUB_OFFLINE
        try {
            $env:PATH = (Join-Path $ProjectRoot '.venv-wlk\Lib\site-packages\torch\lib') + ';' + $savedPath
            $env:HF_HUB_OFFLINE = '1'
            Use-OrStart 'asr' 8000 $AsrPython 'app\.service_host\s+--role\s+asr' 'http://127.0.0.1:8000/health'
        } finally { $env:PATH=$savedPath; $env:HF_HUB_OFFLINE=$savedOffline }
        Write-Host 'ASR listo. Se conservaron Operator, overlay y el registro de la sesion anterior.'
        exit 0
    }
    if ($Action -eq 'Stop') {
        Confirm-Idle
        Stop-Entries $script:LaunchState.services
        $network = Read-Json $NetworkPath
        if ($network) { $network.lan_enabled = $false; Save-Json $NetworkPath $network }
        if (Test-Path -LiteralPath $FirewallPath) {
            if (Test-Administrator) { Remove-OverlayFirewall } else { Invoke-FirewallAction 'CloseFirewall' }
        }
        Save-State
        Write-Host 'Cierre completado. Los servicios anteriores al lanzador se conservan.'
        exit 0
    }
    Confirm-Idle
    $networks = @(Get-LocalNetworks)
    if ($LocalOnly -and $OverlayIP) { throw 'Usa -LocalOnly o -OverlayIP, sin combinarlos.' }
    if (-not $LocalIP -and $networks.Count -eq 1) { $LocalIP = $networks[0].ip }
    Write-Host 'IP de esta PC:'
    $networks | Format-Table @{Label='IPv4';Expression={$_.ip}},@{Label='Red';Expression={$_.interface}},@{Label='Perfil';Expression={$_.profile}}
    if (-not $LocalOnly -and -not $OverlayIP -and -not $SkipPrompts) { $OverlayIP = (Read-Host 'IP de la PC overlay/proyector (opcional; Enter para omitir)').Trim() }
    if (-not $LocalOnly -and -not $LocalIP) {
        if ($SkipPrompts) { throw 'Indica -LocalIP con una IP de la lista anterior.' }
        $LocalIP = (Read-Host 'IPv4 de ESTA PC, de la lista anterior').Trim()
    }
    $selection = @($networks | Where-Object { $_.ip -eq $LocalIP })
    if ($LocalIP -and $selection.Count -ne 1) { throw 'La IP indicada no esta asignada a esta PC.' }
    $lan = -not $LocalOnly
    $priorNetwork = Read-Json $NetworkPath
    if (@(Get-Listeners 3000).Count) {
        $gate = @($script:LaunchState.services | Where-Object { $_.role -eq 'gateway' -and (Get-OwnedProcess $_) })
        if (-not $lan -or -not $gate.Count -or $priorNetwork.local_ip -ne $LocalIP -or $priorNetwork.overlay_access -ne 'any') { throw 'Ya hay una publicacion en 3000. Usa -Action Stop antes de cambiar su configuracion.' }
    }
    if ($lan) { Confirm-LanSelection | Out-Null }
    $network = [pscustomobject]@{local_ip=$LocalIP;local_ips=@($networks.ip);overlay_pc_ip=$OverlayIP;network_profile=$(if ($selection.Count) {$selection[0].profile} else {$null});lan_enabled=$false;overlay_access='any'}
    $previousOwned = @($script:LaunchState.services | Where-Object { $_.owned } | ForEach-Object { $_.run_id })
    $firewallExisted = Test-Path -LiteralPath $FirewallPath
    try {
        Save-Json $NetworkPath $network
        $savedPath = $env:PATH; $savedOffline = $env:HF_HUB_OFFLINE
        try {
            $env:PATH = (Join-Path $ProjectRoot '.venv-wlk\Lib\site-packages\torch\lib') + ';' + $savedPath
            $env:HF_HUB_OFFLINE = '1'
            Use-OrStart 'asr' 8000 $AsrPython 'app\.(asr\.wlk_server|service_host\s+--role\s+asr)' 'http://127.0.0.1:8000/health'
        } finally { $env:PATH=$savedPath; $env:HF_HUB_OFFLINE=$savedOffline }
        Use-OrStart 'api' 8010 $Python '(uvicorn\s+app\.main:app|app\.service_host\s+--role\s+api)' "$ApiCheckBase/health"
        if ($lan) {
            if (Test-Administrator) { Add-OverlayFirewall } else { Invoke-FirewallAction 'Firewall' }
            if (-not @(Get-Listeners 3000).Count) { Start-Owned 'gateway' $Python @('--local-ip',$LocalIP) | Out-Null }
            $deadline = [DateTime]::UtcNow.AddSeconds(15)
            while (-not @(Get-Listeners 3000).Count -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 200 }
            $gate = @($script:LaunchState.services | Where-Object { $_.role -eq 'gateway' -and (Get-OwnedProcess $_) })
            $listeners = @(Get-Listeners 3000)
            if ($gate.Count -ne 1 -or $listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne $LocalIP -or $listeners[0].OwningProcess -ne $gate[0].pid) { throw 'La puerta del overlay no confirmo su inicio.' }
            $network.lan_enabled = $true
            Write-Host "URL para abrir EN LA PC OVERLAY: http://${LocalIP}:3000/overlay"
            if ($OverlayIP -and -not (Test-Connection -ComputerName $OverlayIP -Count 1 -Quiet -ErrorAction SilentlyContinue)) {
                Write-Host 'La PC overlay no respondio al ping; puede tener ICMP bloqueado. Comprueba la URL en su navegador.'
            }
        }
        Save-Json $NetworkPath $network
        Save-State
        Write-Host "TRAD listo. Operator: $ApiBase/operator"
        Write-Host 'No se activo el microfono ni se solicito traduccion. Inicia la lectura desde Operator.'
        Write-Host 'Prueba sencilla: .\Start-TRAD.ps1 -Action Test | Cerrar: .\Start-TRAD.ps1 -Action Stop'
        if (-not $NoBrowser) { Start-Process "$ApiBase/operator" | Out-Null }
    } catch {
        $problem = $_
        $newEntries = @($script:LaunchState.services | Where-Object { $_.owned -and $_.run_id -notin $previousOwned })
        try { Stop-Entries $newEntries } catch { Write-Warning $_.Exception.Message }
        $network.lan_enabled = $false; Save-Json $NetworkPath $network
        if (-not $firewallExisted -and (Test-Path -LiteralPath $FirewallPath)) {
            try { if (Test-Administrator) { Remove-OverlayFirewall } else { Invoke-FirewallAction 'CloseFirewall' } } catch { Write-Warning $_.Exception.Message }
        }
        throw $problem
    }
} catch { Write-Error $_; exit 1 }
finally { if ($locked) { $mutex.ReleaseMutex() }; $mutex.Dispose() }
