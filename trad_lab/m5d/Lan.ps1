[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][ValidateSet('Inspect','Firewall','Start','Close','Status','StopReplay')][string]$Action,
    [string]$Plan,
    [string]$LanIP,
    [string]$ViewerIP,
    [string]$Authorization
)
$ErrorActionPreference = 'Stop'
$root = 'C:\live-captions'
if (!$Plan) {
    $Plan = (Get-Content -LiteralPath "$root\logs\trad_lab\m5d_current_plan.txt" -Raw).Trim()
}
$planPath = (Resolve-Path -LiteralPath $Plan).Path
$data = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
$copy = [IO.Path]::GetFullPath($data.copy)
$runDir = Split-Path -Parent $planPath
if ($data.phase -ne 'M5-D' -or !$copy.StartsWith((Join-Path $root 'logs\trad_lab\'),[StringComparison]::OrdinalIgnoreCase) -or (Split-Path -Leaf $copy) -ne 'copy' -or (Split-Path -Parent $copy) -ne $runDir) {
    throw 'Solo se admite el plan aislado M5-D; LIVE no se modifica.'
}
$runtimeDir = Join-Path $copy '.runtime'
$statePath = Join-Path $runtimeDir 'm5d-processes.json'
$selectionPath = Join-Path $runtimeDir 'm5d-network-selection.json'
$ruleName = 'TRAD-M5D-' + (Split-Path -Leaf (Split-Path -Parent $runDir)) + '-TCP3000'
$python = Join-Path $root '.venv-wlk\Scripts\python.exe'

function Assert-Approval {
    if ($Authorization -ne 'M5-D red autorizada') { throw 'Solicitar autorizacion humana antes de abrir red o iniciar TCP.' }
}
function Assert-IPs {
    if (!$LanIP -and !$ViewerIP -and (Test-Path -LiteralPath $selectionPath)) {
        $selection = Get-Content -LiteralPath $selectionPath -Raw | ConvertFrom-Json
        $script:LanIP = $selection.LanIP
        $script:ViewerIP = $selection.ViewerIP
    }
    foreach ($value in @($LanIP,$ViewerIP)) {
        $address = $null
        if (![Net.IPAddress]::TryParse($value,[ref]$address) -or $address.AddressFamily -ne 'InterNetwork') { throw 'Se requieren ambas IPv4 reales.' }
        $bytes = $address.GetAddressBytes()
        if (!($bytes[0] -eq 10 -or ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or ($bytes[0] -eq 192 -and $bytes[1] -eq 168))) { throw 'Solo IPv4 privadas RFC1918.' }
    }
    if ($LanIP -eq $ViewerIP) { throw 'La IP del espectador debe ser la segunda laptop.' }
    $script:iface = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -eq $LanIP)
    if ($iface.Count -ne 1) { throw 'Seleccionar una IP asignada realmente a esta Alienware.' }
    $profile = Get-NetConnectionProfile -InterfaceIndex $iface[0].InterfaceIndex
    if ($profile.NetworkCategory -ne 'Private') { throw 'La interfaz debe estar en red privada; no se cambia automaticamente.' }
    if (!(Get-NetFirewallProfile -Name Private).Enabled) { throw 'Windows Defender Firewall debe permanecer habilitado.' }
}
function Read-State {
    if (Test-Path -LiteralPath $statePath) {
        $decoded = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        # Windows PowerShell 5 emits a JSON array as one pipeline item. Emit each
        # row explicitly so Close/Status/StopReplay see the same rows on PS 5/7.
        foreach ($entry in $decoded) { $entry }
    }
}
function Assert-Owned($entry) {
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if (!$process) { return $null }
    $info = Get-CimInstance Win32_Process -Filter "ProcessId=$($entry.pid)"
    # PowerShell 7 may deserialize ISO JSON dates as DateTime, whereas Windows
    # PowerShell returns strings. Compare UTC ticks instead of a formatted value.
    $savedStart = [DateTimeOffset]$entry.started
    if ($process.StartTime.ToUniversalTime().Ticks -ne $savedStart.UtcDateTime.Ticks -or !$info.CommandLine.Contains($planPath) -or !$info.CommandLine.Contains('trad_lab.m5d.serve')) {
        throw 'Identidad de proceso distinta; no cerrar un PID reutilizado.'
    }
    return $process
}
function Save-State($entries) {
    ConvertTo-Json -InputObject @($entries) -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8
}

switch ($Action) {
    'Inspect' {
        Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
            Select-Object IPAddress,PrefixLength,InterfaceAlias,InterfaceIndex,PrefixOrigin
        Get-NetConnectionProfile | Select-Object InterfaceAlias,InterfaceIndex,NetworkCategory
        Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -in 3000,8000,8010,18000,18010 |
            Select-Object LocalAddress,LocalPort,OwningProcess
        Get-NetFirewallRule -Name 'TRAD-M5D-*' -ErrorAction SilentlyContinue | Select-Object Name,Enabled,Profile,Action
    }
    'Firewall' {
        Assert-Approval; Assert-IPs
        if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) { throw 'Regla ya existente; inspeccionar o cerrar antes.' }
        if ($PSCmdlet.ShouldProcess("$LanIP`:3000 desde $ViewerIP",'Crear regla Private TCP3000')) {
            New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
            [pscustomobject]@{LanIP=$LanIP;ViewerIP=$ViewerIP} | ConvertTo-Json | Set-Content -LiteralPath $selectionPath -Encoding UTF8
            New-NetFirewallRule -Name $ruleName -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3000 -LocalAddress $LanIP -RemoteAddress $ViewerIP -Profile Private -InterfaceAlias $iface[0].InterfaceAlias -EdgeTraversalPolicy Block | Out-Null
            Write-Output "Regla creada: $ruleName"
        }
    }
    'Start' {
        Assert-Approval; Assert-IPs
        # -WhatIf must not start even loopback services or create runtime state.
        if (!$PSCmdlet.ShouldProcess("$LanIP`:3000 y 127.0.0.1:18010",'Iniciar prueba LAN sin audio ni DeepL')) { return }
        $rule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
        if (!$rule -or $rule.Enabled -ne 'True' -or $rule.Action -ne 'Allow') { throw 'Crear primero la regla privada limitada a la segunda laptop.' }
        $ports = $rule | Get-NetFirewallPortFilter
        $addresses = $rule | Get-NetFirewallAddressFilter
        if ($ports.Protocol -notin 'TCP','6' -or $ports.LocalPort -ne '3000' -or $addresses.LocalAddress -ne $LanIP -or $addresses.RemoteAddress -ne $ViewerIP -or $rule.Profile -ne 'Private') {
            throw 'La regla existente no coincide exactamente con las IP y el puerto autorizados.'
        }
        & $python -c 'import sys; from trad_lab.m5d.prepare import verify; verify(sys.argv[1])' $planPath
        if ($LASTEXITCODE) { throw 'Fallo de manifiesto.' }
        if (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -in 3000,8000,8010,18010) { throw 'Puerto ocupado; no reiniciar servicios existentes.' }
        $entries = @(Read-State)
        foreach ($entry in $entries) { if (Assert-Owned $entry) { throw 'Servicios propios existentes; usar Status.' } }
        New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
        $entries = @()
        # Each role is independent; closing the gateway never stops TRAD.
        foreach ($role in @('trad','gateway')) {
            $stopFile = Join-Path $runtimeDir "m5d-stop-$role"
            if (Test-Path -LiteralPath $stopFile) { Remove-Item -LiteralPath $stopFile }
            $arguments = '-m trad_lab.m5d.serve ' + $role + ' --plan "' + $planPath + '" --authorization "M5-D red autorizada" --lan-ip ' + $LanIP + ' --viewer-ip ' + $ViewerIP
            $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $copy -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runDir "$role.stdout.log") -RedirectStandardError (Join-Path $runDir "$role.stderr.log")
            $entries += [pscustomobject]@{pid=$process.Id;started=$process.StartTime.ToUniversalTime().ToString('o');role=$role;mode='replay'}
            Save-State $entries
            $servicePort = if ($role -eq 'trad') { 18010 } else { 3000 }
            $serviceAddress = if ($role -eq 'trad') { '127.0.0.1' } else { $LanIP }
            $startupClock = [Diagnostics.Stopwatch]::StartNew()
            $ready = $false
            while ($startupClock.Elapsed.TotalSeconds -lt 15) {
                $process.Refresh()
                if ($process.HasExited) { break }
                $listener = @(Get-NetTCPConnection -State Listen -LocalPort $servicePort -ErrorAction SilentlyContinue)
                if ($listener.Count -eq 1 -and $listener[0].LocalAddress -eq $serviceAddress) {
                    $listenerProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener[0].OwningProcess)"
                    # Windows venv can use a child Python executable. Require the
                    # exact role/plan and either the saved PID or its direct child.
                    if ($listenerProcess.CommandLine -and $listenerProcess.CommandLine.Contains($planPath) -and $listenerProcess.CommandLine.Contains("trad_lab.m5d.serve $role ") -and ($listenerProcess.ProcessId -eq $process.Id -or $listenerProcess.ParentProcessId -eq $process.Id)) {
                        $ready = $true
                        break
                    }
                }
                Start-Sleep -Milliseconds 250
            }
            if (!$ready) { throw "No se confirmo $role listo en su direccion exacta; consultar su log. No hay reintento automatico. Usar Close." }
            if ($role -eq 'trad') {
                $capabilities = Invoke-RestMethod -Uri 'http://127.0.0.1:18010/m5c/capabilities' -TimeoutSec 3
                if ($capabilities.phase -ne 'M5-D replay' -or $capabilities.physical_enabled -or $capabilities.real_deepl_enabled) { throw 'TRAD no confirmo modo sin audio ni DeepL.' }
            }
        }
        Write-Output "Laptop B: http://$LanIP`:3000/overlay"
        Write-Output 'Alienware: http://127.0.0.1:18010/operator (usar botones PRUEBA LAN)'
    }
    'Status' {
        foreach ($entry in @(Read-State)) {
            $process = Assert-Owned $entry
            [pscustomobject]@{Role=$entry.role;PID=$entry.pid;Running=($null -ne $process)}
        }
        Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -in 3000,18010 | Select-Object LocalAddress,LocalPort,OwningProcess
    }
    'Close' {
        if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) {
            if ($PSCmdlet.ShouldProcess($ruleName,'Retirar solo regla M5-D')) { Remove-NetFirewallRule -Name $ruleName }
        }
        $entries = @(Read-State)
        foreach ($entry in $entries | Where-Object role -eq 'gateway') {
            $process = Assert-Owned $entry
            if ($process -and $PSCmdlet.ShouldProcess("PID $($entry.pid)",'Cerrar solo puerta LAN')) {
                Set-Content -LiteralPath (Join-Path $runtimeDir 'm5d-stop-gateway') -Value 'stop' -Encoding ASCII
                if (!$process.WaitForExit(12000)) { throw 'La puerta no confirmo cierre. La regla ya fue retirada; revisar PID sin reiniciar TRAD.' }
            }
        }
        Write-Output 'La operacion local TRAD y ASR no se detiene. Conservar evidencia.'
    }
    'StopReplay' {
        foreach ($entry in @(Read-State) | Where-Object { $_.role -eq 'trad' -and $_.mode -eq 'replay' }) {
            $process = Assert-Owned $entry
            if ($process -and $PSCmdlet.ShouldProcess("PID $($entry.pid)",'Cerrar TRAD de prueba sin ASR')) {
                Set-Content -LiteralPath (Join-Path $runtimeDir 'm5d-stop-trad') -Value 'stop' -Encoding ASCII
                if (!$process.WaitForExit(12000)) { throw 'No se confirmo cierre del TRAD de prueba; revisar PID.' }
            }
        }
    }
}
