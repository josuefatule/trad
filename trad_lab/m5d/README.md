# M5-D: overlay LAN de solo lectura

Preparación sin abrir red. Informe completo: `C:/live-captions/S2-M5D-LAN-OVERLAY-REPORT.md`.
Se clona el plan M5-C2 reparado; renderer, Hub, CSS, ASR, FIR, crédito y DeepL
quedan idénticos. El modo predeterminado `replay` bloquea captura y proveedor.
La puerta solo conecta con TRAD `127.0.0.1:18010`. No existe proxy de uso general.
Durante replay, cada página de prueba permanece al menos diez segundos para
permitir la comprobación humana en la otra laptop. Esta configuración solo se
aplica al replay; los tiempos del modo live y el renderer permanecen originales.

## Operador: cuatro comandos, únicamente tras autorización

Primero conectar ambas laptops a una red privada de confianza. Consultar el IPv4
de B en Configuración de Windows o `Get-NetIPAddress -AddressFamily IPv4` en B.
No adivinar las IP. El script no cambia perfiles ni direcciones de red.

1. PowerShell normal, Alienware:

   ```powershell
   C:\live-captions\trad_lab\m5d\Lan.ps1 -Action Inspect
   ```

2. PowerShell **administrador**, Alienware; introducir ambas IP reales cuando se
   soliciten. **Este paso abre el firewall y requiere autorización previa**:

   ```powershell
   C:\live-captions\trad_lab\m5d\Lan.ps1 -Action Firewall -LanIP (Read-Host 'IPv4 privada Alienware') -ViewerIP (Read-Host 'IPv4 segunda laptop') -Authorization 'M5-D red autorizada'
   ```

3. PowerShell **normal**, Alienware. Recupera las IP del paso anterior y las
   revalida. Arranca únicamente TRAD de prueba loopback y puerta LAN:

   ```powershell
   C:\live-captions\trad_lab\m5d\Lan.ps1 -Action Start -Authorization 'M5-D red autorizada'
   ```

   Abrir Operator local: `http://127.0.0.1:18010/operator`. Usar **Iniciar prueba
   LAN**, **Siguiente caption**, los controles originales CLEAR/OCULTAR/REANUDAR
   y **Terminar prueba LAN**. El START de micrófono está bloqueado. Los captions
   de prueba están marcados; no consumen ASR ni DeepL. La laptop B abre la URL
   impresa por Start, con `/overlay` y sin parámetros. Tamaño OBS futuro 1920×1080;
   abrir OBS necesita autorización aparte.

4. PowerShell **administrador**, Alienware, cerrar publicación:

   ```powershell
   C:\live-captions\trad_lab\m5d\Lan.ps1 -Action Close
   ```

   Retira solo la regla M5-D y cierra de forma ordenada la puerta. TRAD queda
   disponible localmente. Para finalizar también **solo el TRAD de replay** tras
   terminar la prueba: `Lan.ps1 -Action StopReplay` (mantenimiento adicional).

`-Action Status` muestra procesos/listeners propios. `-WhatIf` permite revisar
Firewall/Start/Close sin ejecutarlos. El firewall admite TCP 3000, IP local exacta,
IP B exacta, interfaz elegida y perfil Private; no abre 18000/18010/8000/8010.
No se cambia ExecutionPolicy: si Windows bloquea scripts, revisar la política
con el administrador. No desactivar firewall ni controles del sistema.

## Pruebas sin TCP

Desde la copia congelada y con el plan correspondiente:

```powershell
C:\live-captions\.venv-wlk\Scripts\python.exe -m trad_lab.m5d.check --plan RUTA_REAL_PLAN --out NUEVO_DIRECTORIO_RESULTADOS
```

`check_browser.cjs` prueba las regresiones originales con host remoto;
`check_wire.cjs` pasa el wire ASGI al overlay real; `check_powershell.ps1 -Plan
RUTA_REAL_PLAN` usa dobles de firewall y de procesos. Los únicos valores
192.168.50.10/20 del código son fixtures en memoria; nunca se asignan ni enlazan.

## Servicios de producción experimental futuros

La primera prueba física será replay: no hace falta Turbo. Tras autorizaciones
adicionales independientes, `serve.py` admite backend Turbo y TRAD con el mismo
proveedor M5-C2. Desde la copia verificada y con `--plan` explícito:

* `python -m trad_lab.m5d.serve backend --mode live --plan RUTA_REAL_PLAN
  --authorization 'M5-D Turbo autorizado'`: loopback 18000.
* `python -m trad_lab.m5d.serve trad --mode live --plan RUTA_REAL_PLAN
  --authorization 'M5-D TRAD con DeepL autorizado'`: loopback 18010. Requiere el
  backend anterior y usa la fábrica DeepL original; no iniciar sin permiso.
* `python -m trad_lab.m5d.serve gateway --plan RUTA_REAL_PLAN --lan-ip IP_REAL_A
  --viewer-ip IP_REAL_B --authorization 'M5-D red autorizada'`: IP privada:3000.

Estos comandos son procedimientos preparados, no ejecutados. No mezclar un TRAD
de replay ya iniciado con otro TRAD live. El cierre de gateway sigue independiente.
