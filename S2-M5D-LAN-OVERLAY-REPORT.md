# TRAD — Sprint 2 / M5-D: publicación segura del overlay por LAN

22 de octubre de 2026, America/La_Paz.

**Estado actual: GO CON RESERVAS para visualización LAN en navegador.** El usuario
autorizó y completó la prueba desde una Dell con Ubuntu, IP `10.0.0.105`, hacia
la Alienware `10.0.0.88`. Se confirmaron captions, CLEAR, OCULTAR/REANUDAR,
recuperación tras interrupción Wi-Fi y rechazo de Operator. Al terminar se cerraron
los servicios, se retiró la regla y se restauró el perfil original **Public**.
La URL no queda sirviendo después del cierre. Evidencia y límites en §11.

Las secciones 1–10 conservan la preparación anterior a la autorización. Su NO-GO
inicial por perfil Public/IP B desconocida queda superado por el ensayo de §11;
no se presenta aquel estado inicial como el resultado físico final.

## 1. Auditoría, aislamiento y preservación

Se revisaron M5-C §§14–16, M5-B §17, BIDIRECTIONAL_MVP_REPORT,
INSTALL_WINDOWS y el código real de CaptionHub, renderer, WebSocket, Operator,
autenticación y ocultación. Se conserva el resultado anterior de 140/140 registros
ASR entregados y 29/29 traducciones, sin convertirlo en una certificación OBS.
El error `140 over 90 → 140 over 19` sigue documentado y no se corrigió.

Git real: rama `sprint2/m1-rtx4070`; HEAD/main permanecen en
`64f82214b33fad4ee68295df1367249caeae3187`; checkpoint `codex/s2-m4-checkpoint`
en `cd008ad436d8d2c13a739490e899d18e188df9b3`. El tag anotado `v0.1.0-rc1`
conserva su objeto `87a25e093c673d9594407188efa00854826eccb6`.
Se preservan los 18 archivos versionados previamente modificados y todo el
trabajo sin seguimiento anterior. No se hizo commit, tag, merge, push, reset ni release.

Run privado: `C:/live-captions/logs/trad_lab/m5d_20261022T040503Z`.
`audit.json` y `pre_m5d_sources.zip` conservan el inventario inicial de 842 fuentes
y los hashes de 9221 archivos históricos. `.env` se verifica únicamente por hash
en la preservación; no se copian ni publican sus credenciales.
La comprobación final queda en `preservation_final.json`.
Resultado: **PASS**, cero fuentes originales o archivos históricos alterados,
`.env` idéntico y todas las referencias Git intactas.

Base: plan M5-C2 reparado de 195 archivos,
`logs/trad_lab/m5c2repair_20261022T020037Z/environment_repaired_ready/plan.json`,
SHA-256 `21e9f77888844103adb7f9ecfbc962db4cd9ee173e488ee9140da4df770dc03c`.

**Copia final M5-D, 208 archivos congelados:**

`C:/live-captions/logs/trad_lab/m5d_20261022T040503Z/environment_final/copy`

Plan hermano: `environment_final/plan.json`, SHA-256
`ed1f4ecc76c96421d82722c68b19ba1a6847a8156199b4d29962d0750870cc6d`.
Su verificación se registra en `preservation_final.json`. Los candidatos intermedios se conservan;
el puntero privado `logs/trad_lab/m5d_current_plan.txt` selecciona solo este plan.
Las autorizaciones anteriores B/DeepL no se heredan: el plan nuevo declara
`default_mode=replay`, `deepl_enabled=false`, `network_authorized=false`.

## 2. Arquitectura y decisiones de seguridad

```text
Laptop B, IP explícitamente autorizada
  http://IP_PRIVADA_A:3000/overlay
             │ HTTP GET + WebSocket v3
             ▼
  Puerta M5-D, enlazada solo a IP_PRIVADA_A:3000
    ├─ HTML/CSS/JS de la copia verificada
    ├─ GET fijo a 127.0.0.1:18010/api/overlay/config
    └─ suscripción fija a ws://127.0.0.1:18010/ws/overlay
                         │
                CaptionHub original
                         │
  prueba inicial: captions sintéticos locales, sin audio/ASR/DeepL
  futuro autorizado: cadena M5-C2 → Turbo 127.0.0.1:18000 / DeepL original
```

No hay otro Hub, renderer o protocolo de subtítulos. Se conserva byte por byte
`caption_renderer.js`, `overlay.js`, `overlay_geometry.js`, `overlay_latency.js`,
CSS y CaptionHub del M5-C2 reparado. El modo sigue siendo `timed_queue`, con
canvas 1920×1080, fuente de 48 px y región inferior de 150 px: caben dos líneas
efectivas. No cambian Turbo, pcm_credit_v1, FIR, Worklet, SegmentManager,
TranscriptState, normalización, proveedor DeepL ni sus parámetros.

La puerta es un proceso independiente. No importa ni inicia la aplicación ASR;
solo lee la configuración pública y la suscripción existente. Desactivar la
puerta libera sus suscriptores sin enviar STOP, CLEAR u otros comandos a TRAD.

### Capacidad de visualización y autenticación

El `/ws/overlay` existente no requiere token de Operator; admite exclusivamente
telemetría validada. La puerta no cambia ese contrato interno ni comparte tokens.
La capacidad remota se limita mediante IP de B exacta, IP local exacta, interfaz
Private y firewall. También se verifica el peer real en ASGI. No se confía en
X-Forwarded-For; Uvicorn usa `proxy_headers=False`.

Host debe coincidir exactamente con `IP_A:3000`. WebSocket requiere Origin
`http://IP_A:3000`; HTTP rechaza orígenes distintos y navegación cross-site.
Se rechazan consultas, incluidos tokens o cambios de geometría en URL. Cookies,
cabeceras de autorización y subprotocolos del cliente no se reenvían a TRAD.
No se propagan Set-Cookie, redirects ni mensajes de error internos.

La allowlist usa rutas concretas: no hay montaje de directorios ni proxy genérico.
Los accesos llevan `no-store`, CSP restringida, `nosniff`, prohibición de iframe y
Permissions-Policy sin micrófono/cámara. No se registran URLs, cookies, captions
o payloads de espectadores en access logs; estos están desactivados.

Esta capacidad por IP no autentica criptográficamente un dispositivo. HTTP/WS no
cifran el contenido. El alcance es una red privada de confianza con acceso
supervisado; no una red pública, Wi-Fi de invitados ni publicación por Internet.
No se abre el router, UPnP, DMZ o port forwarding.

## 3. Rutas y métodos publicados

| Método | Ruta | Fuente |
|---|---|---|
| GET | `/overlay` | Plantilla real M5-C2; rótulo M5-D de ensayo |
| GET | `/static/overlay.css` | CSS original |
| GET | `/static/overlay_geometry.js` | Geometría original |
| GET | `/static/caption_renderer.js` | Renderer original reparado |
| GET | `/static/overlay_latency.js` | Calibración original |
| GET | `/static/overlay.js` | Recepción/reconexión original |
| GET | `/api/overlay/config` | Lectura fija loopback; esquema visual exacto validado |
| WebSocket | `/ws/overlay` | Suscriptor de lectura loopback; JSON de eventos íntegro |

Los demás métodos y rutas HTTP devuelven 404; WebSockets no autorizados se cierran.
Esto incluye `/operator`, CAPTURE, `/ws/session`, bootstrap, recuperación,
START/STOP/CLEAR, ocultación, endpoints de replay, `/health`, status/diagnósticos,
preview, documentación API, `.env`, `.runtime`, logs, corpus y código fuente.

## 4. WebSocket, orden, reconexión y límites

El código original construye `ws://location.host/ws/overlay` o WSS si corresponde.
Desde B utiliza la IP de A y el puerto 3000; nunca intenta conectar a localhost
de B. Configuración y recursos usan el mismo origen.

Cada espectador tiene un suscriptor original. Los eventos v3 pasan como el mismo
JSON recibido, conservando texto, IDs, sesión, orden, secuencia, idioma y generación
visual. No hay caché de captions ni journal de replay en la puerta. Solo se admite
destino ES; una dirección diferente cierra la suscripción.

Los mensajes del espectador **nunca se envían al WebSocket interno**. `clock_probe`
obtiene respuesta local con el reloj monotónico del mismo Windows que CaptionHub.
`render_sample`, `connection_health` y `display_drop` solo alimentan un buffer
local de metadatos numéricos, de 128 entradas, sin texto. Comandos, JSON inválido,
binarios y payloads de más de 8 KiB cierran al espectador.

Límites: cuatro conexiones remotas, 60 mensajes/segundo/conexión, upstream con
cuatro elementos pendientes, 1 MiB por evento y dos segundos para enviar al visor.
Un espectador lento se desconecta; no puede bloquear indefinidamente la cadena
ASR. No hay reintento de comandos ni acumulación ilimitada de captions.

CLEAR y OCULTAR conservan generación y watermark. Lo ocultado no se repite al
REANUDAR. La reconexión recibe únicamente el snapshot original vigente; conserva
la deduplicación original y los watermarks. Una recarga completa puede restaurar
el caption actual todavía válido, conforme al contrato original; no reproduce
todo el historial. Se mantienen ocho intentos con backoff y recarga manual al agotarlos.
Una nueva sesión reinicia la secuencia y descarta contenido de sesiones anteriores.

## 5. Archivos nuevos y diferencias de la copia

Código nuevo exclusivamente en `trad_lab/m5d/`:

| Archivo | Finalidad |
|---|---|
| `gateway.py` | Allowlist HTTP/WS, peer/Host/Origin, suscripción de lectura y límites |
| `prepare.py` | Copia aislada, manifiesto y protección de fuentes M5-C2 |
| `serve.py` | Launchers autorizados, IP asignada/Private, cierre independiente |
| `runtime.py`, `replay.js` | Prueba local autenticada con cinco captions marcados, sin audio/proveedor |
| `Lan.ps1` | Inspección, firewall, arranque de replay, estado y cierre reversibles |
| `check.py` | Integración real ASGI en memoria y pruebas hostiles |
| `check_browser.cjs`, `check_wire.cjs` | Renderer original con host remoto y eventos reales en memoria |
| `check_powershell.ps1` | Autorización, IP, Private y WhatIf mediante dobles sin efectos |
| `check_launchers.py` | Regresión del guardado al cerrar, con servidor simulado sin TCP |
| `README.md`, `__init__.py` | Operación y módulo |

De los 195 archivos históricos, **192 siguen idénticos**. Solo en la copia cambian:

1. `app/main.py`: hooks M5-D de configuración/instalación y selección del proveedor.
2. `app/templates/overlay.html`: rótulo honesto `M5-D · OVERLAY LAN · ENSAYO`.
3. `app/templates/operator.html`: carga del control de replay local.

Se añade `app/static/m5d_replay.js`; no se publica en la puerta LAN. El modo
replay bloquea también `/ws/session` y las páginas de captura en el servidor.
Solo un Operator local autorizado inicia/avanza/termina el replay y adquiere su
propiedad. CLEAR/OCULTAR/REANUDAR usan sus endpoints originales. La recuperación
de Operator invalida el token anterior también para replay.

El modo live preparado delega a los hooks y proveedor M5-C2 originales; exige
autorizaciones separadas. No fue iniciado ni habilitado por esta preparación.
No se modifica `app/` LIVE ni sus puertos 8000/8010.

## 6. IP real, red y firewall reversible

Consulta PowerShell, sin cambiar configuración:

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Select-Object IPAddress,PrefixLength,InterfaceAlias,InterfaceIndex,PrefixOrigin
Get-NetConnectionProfile | Select-Object InterfaceAlias,InterfaceIndex,NetworkCategory
```

Observado: Wi-Fi, índice 11, IPv4 DHCP `10.0.0.88`, perfil **Public**. Es una
observación dinámica, no una asignación. La URL prevista con esa IP sería
`http://10.0.0.88:3000/overlay`, **actualmente sin servicio publicado**. Consultar
otra vez después de conectar a la red privada; usar la IP real resultante.
Las direcciones 192.168.50.10/20 de los tests son fixtures: nunca se enlazaron ni
se asignaron a Windows. Aún no se conoce la IP real de B.

La regla preparada se llama
`TRAD-M5D-m5d_20261022T040503Z-TCP3000`. Es inbound Allow, TCP 3000, LocalAddress
IP_A exacta, RemoteAddress IP_B exacta, interfaz elegida, perfil Private y
EdgeTraversal bloqueado. No se abre ninguna regla si falta B o la interfaz no
es Private. El arranque revalida la regla, la IP asignada y el firewall habilitado.

`Lan.ps1 -Action Close` retira únicamente esa regla y solicita cierre ordenado
al proceso propio de gateway. Verifica PID/fecha/comando; no mata procesos ajenos
ni TRAD/Turbo. Si el cierre no confirma su plazo, informa el fallo con la regla ya
retirada. No se cambia IP, perfil, DNS, gateway, router o ExecutionPolicy; nunca
se desactiva Windows Defender Firewall.

Para mañana: coordinar una red privada dedicada con el equipo audiovisual y, si
el administrador lo permite, reservas DHCP para ambas laptops. Confirmar que
no haya aislamiento entre clientes Wi-Fi. Estas son recomendaciones; no se
configuran automáticamente. No marcar como privada una red pública para eludir
la barrera del launcher.

## 7. Procedimiento del operador: cuatro comandos

**No ejecutados. Requieren autorización previa y red privada de confianza.**
La IP B se consulta en esa laptop. El script pide ambos valores reales y conserva
la selección localmente; el siguiente paso vuelve a validarla.

1. PowerShell normal en Alienware:

   ```powershell
   C:\live-captions\trad_lab\m5d\Lan.ps1 -Action Inspect
   ```

2. PowerShell administrador en Alienware, después de aprobar apertura:

   ```powershell
   C:\live-captions\trad_lab\m5d\Lan.ps1 -Action Firewall -LanIP (Read-Host 'IPv4 privada Alienware') -ViewerIP (Read-Host 'IPv4 segunda laptop') -Authorization 'M5-D red autorizada'
   ```

3. PowerShell normal en Alienware:

   ```powershell
   C:\live-captions\trad_lab\m5d\Lan.ps1 -Action Start -Authorization 'M5-D red autorizada'
   ```

   Confirma listeners propios en las direcciones exactas y capacidades replay.
   Inicia TRAD `127.0.0.1:18010` y la puerta IP_A:3000, sin Turbo. No es necesario
   cargar GPU para probar la visualización. Imprime la URL real para B y la de
   Operator `http://127.0.0.1:18010/operator` para A. Si un arranque falla, se
   conserva el log y no se reintenta automáticamente.

4. PowerShell administrador, después de terminar la prueba:

   ```powershell
   C:\live-captions\trad_lab\m5d\Lan.ps1 -Action Close
   ```

La terminación del replay se hace primero con su botón local. Close cierra
solamente la publicación; mantiene TRAD local. `-Action StopReplay` es el cierre
adicional del TRAD de prueba, sin sesión ASR. `-Action Status` permite inspección.
Para revisar sin ejecutar Firewall/Start/Close, añadir `-WhatIf`.

Los launchers de Turbo 18000 y TRAD live 18010 están documentados en
`trad_lab/m5d/README.md`; requieren aprobaciones separadas y no forman parte de
esta primera prueba. La frase de autorización es un seguro operativo, no una
credencial de red. No abrir micrófono, DeepL real, OBS o proyección por ejecutar
este procedimiento de replay.

## 8. Pruebas automatizadas y evidencia

| Grupo | Resultado y alcance |
|---|---|
| TRAD real → gateway → espectador ASGI | **165 comprobaciones PASS**, copia final; 18 suscripciones abiertas y 18 liberadas |
| HTTP y secretos | HTML y cinco assets exactos; config validada; rechazo de rutas privadas, métodos, traversal, queries, Host/Origin y otros peers; no cookies |
| Controles originales | CLEAR, OCULTAR, snapshot vacío al reconectar oculto, REANUDAR solo nuevo, nueva sesión, token recuperado y anterior revocado |
| Mensajes hostiles | START/STOP/CLEAR/OCULTAR/REANUDAR/publicación remota, JSON inválido, binarios, esquema y tamaño rechazados sin mutar TRAD |
| Cierre | Gateway cancelado con sesión aún live: estado/propietario intactos y cero suscriptores huérfanos |
| Regresiones Python | **67 tests PASS**, traducción simulada, Hub, contratos C1, crédito/flujo, transporte y adaptador; sin servicios TCP |
| Renderer y geometría | Suites originales contra assets de la copia con host remoto; socket usa exactamente IP_A:3000; reconexión, CLEAR, snapshots obsoletos y sesiones PASS |
| Eventos ASGI → DOM | 31 eventos de la integración, cuatro captions exactos y cuatro CLEAR vacíos, con overlay.js/renderer originales y navegador simulado |
| Replay conservado de presentación | 51/51 captions españoles íntegros; cero drops; hasta dos páginas en cola; caso largo de cuatro páginas sin pérdida |
| Chrome headless real | Canvas/DOM con las 51 traducciones conservadas por file://; dos líneas sin recorte inspeccionadas en captura 1920×1080 |
| UI de replay local | Botones, token recuperado y bloqueo de START de micrófono PASS en VM; sin APIs nativas |
| PowerShell | Ocho controles de autorización/IP/Private/WhatIf PASS con dobles; cero reglas creadas y cero procesos iniciados |
| Compilación/sintaxis | Python, JavaScript y parser PowerShell PASS |

Evidencia principal bajo el run: `checks_release/result.json`,
`checks_release/wire.json`, `python_regressions_final.log`, `browser_final.log`,
`presentation_final.log`, `wire_dom_final.log`, `replay_ui_final.log`,
`powershell_release.log`, `render_final/result.json`, `render_final/overlay.png`,
`preservation_final.json` y `network_closure.json`.

La copia `environment_final` conserva los mismos assets/app ya renderizados y
probados en `environment_ready`; el último ajuste solo mejora el preflight y
espera de readiness del script PowerShell. Se repitió ASGI y WhatIf contra el
plan final. Su arranque de procesos/firewall real permanece deliberadamente sin
ejecutar. Los resultados anteriores se conservan, sin sobrescribirlos.

Un proceso Python inicial se bloqueó antes de iniciar la batería al crear el
socketpair interno de asyncio dentro del sandbox Windows. Se identificaron y
cerraron únicamente sus dos PIDs 39628/22616. La misma batería pasó con permiso
de ejecución y transportes ASGI; el test prohíbe bind/listen de aplicación y
DeepL real. No se abrió un servidor para superar ese bloqueo.
El primer fixture PowerShell tenía un error de alcance de variables de sus
dobles; se corrigió el harness y pasó sin cambiar reglas reales.

No se ejecutó inferencia GPU, micrófono, DeepL real, OBS ni ensayo entre laptops.
La transparencia está comprobada por CSS/configuración y DOM; el fondo blanco
de la captura headless no es una certificación de alpha de OBS. Tampoco se
declara una nueva latencia LAN a partir de estas pruebas.

## 9. Ensayo supervisado con dos laptops y medición

Después de aprobación, confirmar ambas IP, red privada de confianza, regla y
listener IP_A:3000. A mantiene Operator exclusivamente en loopback. B abre en
Chrome o Edge la URL impresa, sin instalar TRAD. No abrir OBS en esta primera
fase; su Browser Source requiere una autorización y comprobación posteriores.

1. A abre Operator local y pulsa **Iniciar prueba LAN**. B confirma carga y
   WebSocket conectado desde herramientas de desarrollador → Network → WS.
2. A pulsa **Siguiente caption**. Confirmar texto español marcado PRUEBA LAN,
   idioma ES, secuencia y fondo transparente por CSS. La marca de ensayo sigue
   visible; no se presenta como un feed certificado del congreso.
3. Aplicar CLEAR desde Operator: B queda vacío. Publicar el siguiente caption.
4. Pulsar OCULTAR y después Siguiente caption: B permanece vacío. Pulsar
   REANUDAR y Siguiente caption: aparece solo el nuevo texto, no el ocultado.
5. Recargar B y después desconectar/reconectar brevemente su red. Confirmar
   deduplicación, watermark y ausencia de historial antiguo; si se agotan los
   ocho reintentos, recargar manualmente. Terminar y comenzar una nueva prueba
   desde A para confirmar sesión nueva y secuencia 1.
6. Desde B comprobar rechazo de `/operator`, `/api/operator/bootstrap`,
   `/api/operator/status`, `/api/m5c/presentation`, `/ws/session` y archivos privados.
7. A termina el replay y ejecuta Close. B pierde la publicación. Confirmar que
   el Operator local y TRAD siguen disponibles y la regla desapareció. Conservar
   los registros. No reiniciar ASR como parte de ese cierre.

Registrar IP de ambos equipos, perfil, navegador/versión, viewport 1920×1080,
sesión, secuencias, generación, timestamps y estado WS. No publicar tokens,
cookies, `.env` o transcripciones privadas en el acta.

El renderer original emite `clock_probe` y `render_sample`. La puerta responde
con el mismo dominio monotónico del Windows de CaptionHub; el cálculo original
correlaciona `published_mono_ms` con recepción/render del navegador. Al cerrar
ordenadamente se escribe `environment_final/gateway_samples.json`, limitado a
las últimas 128 observaciones numéricas. Para la prueba corta, conservar además
la secuencia de eventos WS en B y sus momentos locales de recepción.

Informar por separado publicación Hub→recepción estimada, incertidumbre de
sincronización, demora de renderer/cola y doble requestAnimationFrame. Los samples
de CLEAR carecen de demora de presentación y no se cuentan como captions visibles.
No sumar relojes de máquinas diferentes sin calibración ni presentar rAF como
fotones. Alpha efectivo, OBS, salida audiovisual y presentación física requieren
otra medición; no hay valores de latencia física certificados en M5-D.

## 10. Aceptación, rollback, pendientes y dictamen

La preparación cumple URL de un mismo origen para HTTP/WS, renderer original,
lectura estricta, controles/sesiones preservados, archivos privados inaccesibles,
ausencia de credenciales remotas y procedimiento reproducible. Las pruebas no
detectan nuevas pérdidas, alteraciones o duplicaciones en los captions ejercitados.

Falta certificar entre dos laptops: alcance del firewall real, acceso y
reconexión Wi-Fi, compatibilidad del navegador remoto, controles físicos y
mediciones LAN. La latest corrección de presentación sigue sin certificación OBS.
Los problemas médicos y de traducción históricos no se consideran corregidos.

Ante cualquier fallo: no ampliar la allowlist ni abrir todos los perfiles.
Cerrar solo la puerta y su regla; conservar el run. No detener una sesión ASR
activa para hacer rollback de LAN. En replay, terminar con el botón y, si se desea,
cerrar después su TRAD con StopReplay. No hay restauración que aplicar a LIVE:
su código/puertos y todos los checkpoints permanecen intactos.

Antes de continuar se necesita: confirmación de una red privada de confianza,
IP real de B y autorización para firewall TCP 3000, TRAD de replay en loopback,
puerta LAN y ensayo supervisado. El perfil actual no se modifica sin una
autorización específica; puede seleccionarse otra red privada dedicada.

**Dictamen histórico de preparación: NO-GO hasta recibir IP B y autorización.**
La sección siguiente registra su autorización, ejecución y dictamen actualizado.

## 11. Ensayo LAN autorizado: Alienware → Dell Ubuntu

22 de octubre de 2026, America/La_Paz. Run del ensayo:
`logs/trad_lab/m5d_20261022T040503Z/lan_trial_20261022T043458Z`.

El usuario proporcionó `10.0.0.105`, identificó la Dell de trabajo con Ubuntu,
confirmó que la red de su segunda casa es de confianza y pidió continuar la
prueba. Se ejecutó exclusivamente replay. No se abrió micrófono, Turbo, DeepL
real, OBS o proyección. No hubo cambios de IP, router o puertos LIVE.

### Red real y alcance autorizado

Se revalidó `10.0.0.88/24`, Wi-Fi, interfaz 11. Tras aprobación de Windows UAC,
el perfil de esa conexión se cambió temporalmente de Public a Private y se creó
la regla exacta TCP 3000, IP local `10.0.0.88`, RemoteAddress `10.0.0.105`,
interfaz Wi-Fi, perfil Private. Se conservó su estado anterior para restauración.
`network_before.json`, `network_open_result.json` y `services_ready.json`
registran la operación. La petición de la propia Alienware a la puerta obtuvo
404, conforme al límite exclusivo a la Dell.

Los únicos listeners de prueba fueron `127.0.0.1:18010` y `10.0.0.88:3000`.
Se observó una conexión TCP establecida con RemoteAddress `10.0.0.105` y un
suscriptor de CaptionHub. El usuario confirmó que el rótulo M5-D cargó en la Dell.

### Primera observación y ventana de lectura

La primera sesión `lan-replay-1f87fbc83de3` produjo captions muy breves, con la
duración de lectura original aproximada de dos o tres segundos. El usuario no
observó el primero, sí observó el segundo y no observó el caption de REANUDAR.
No se transforman esos resultados en un PASS ni se adjudica una pérdida de red
solo por la ausencia de observación humana. No hay telemetría final de esa fase:
el guardado del launcher falló al cerrar, como se detalla abajo.

Para coordinar el ensayo se preparó otra copia. **Solo en replay**, la
configuración usa `min_display_ms=10000`, `max_display_ms=30000`. El renderer,
geometría, textos, protocolo y tiempos del modo live quedan originales. No se
modificó ninguna copia congelada previa. La Dell recargó la misma URL para
recibir la configuración nueva; el usuario confirmó que ahora se veía bien.

### Confirmaciones físicas y telemetría del renderer

Sesión final `lan-replay-1177db7e6712`, ejecutada con
`environment_human3/plan.json` y `.venv-wlk`.

| Comprobación | Resultado |
|---|---|
| HTML real por LAN | Usuario confirmó rótulo M5-D en Dell Ubuntu |
| Caption 1 | Usuario confirmó texto visible con la duración ampliada |
| Caption 2 + CLEAR | Usuario confirmó aparición y borrado antes de diez segundos |
| OCULTAR + caption 3 | Suprimido en Hub, sin caption actual; usuario confirmó que no apareció |
| REANUDAR + caption 4 | Usuario confirmó solo el nuevo texto, sin repetir el ocultado |
| Recarga | El usuario recargó y confirmó que volvió el rótulo y posteriormente el caption |
| Interrupción Wi-Fi | Usuario apagó/reconectó Wi-Fi de la Dell, manteniendo la pestaña abierta |
| Caption 5 tras recuperar Wi-Fi | Usuario confirmó solo «Café, presión y secuencia: 1, 2, 3.», sin textos antiguos |
| `/operator` desde la Dell | Usuario confirmó rechazo, sin controles locales expuestos |
| Cierre independiente de la puerta | Puerto 3000 cerrado; misma sesión local live, secuencia 5 y generación 4 preservadas |
| Fin del replay | Botón local llevó la sesión a stopped; después se cerró únicamente ese TRAD |

La telemetría final contiene **13 registros** y cuatro muestras de presentación
de las secuencias **1, 2, 4, 5**, una vez cada una; la 3 fue ocultada
intencionalmente. El caption 4 reportó dos líneas; los demás, una.
Hub informó cero errores de broadcast y cero drops; la puerta conserva además
los samples DOM sin depender de la telemetría de Operator.

El CLEAR del caption 2 se observó en DOM unos **4898,1 ms** después de su
recepción, antes del mínimo de diez segundos. La secuencia oculta 3 no tiene
muestra de presentación; el siguiente render es la 4 en generación 3. El último
caption llega en generación 4, watermark 4, tras el corte de Wi-Fi.

Durante el corte breve de Wi-Fi no se acredita un nuevo handshake WebSocket:
el TCP puede sobrevivir esa interrupción. Se confirma recuperación de recepción
y ausencia de captions antiguos por declaración del usuario y sample posterior.
Las reconexiones forzadas, límites y aislamiento entre sesiones conservan además
sus pruebas ASGI/renderer; no se etiquetan como nuevos casos físicos completos.

### Latencia medida y límites

Cuatro muestras de captions; valores en milisegundos:

| Intervalo | Mínimo | Mediana | Máximo |
|---|---:|---:|---:|
| Publicación Hub → recepción estimada en Dell | 27,65 | 64,25 | 84,75 |
| Recepción → doble requestAnimationFrame | 6,10 | 11,70 | 17,20 |

La incertidumbre de entrega informada por la calibración fue **17,38–19,88 ms**.
Son estimaciones del reloj/DOM del navegador, con solo cuatro captions de prueba.
No son latencia física de pantalla, fotones, OBS, audio→ASR ni DeepL; no se
generaliza un p95 de este grupo mínimo. La transparencia sigue sustentada por
CSS/configuración y las pruebas de renderer; alpha de OBS/composición física
permanece sin certificar.

Evidencia: `gateway_samples_actual.json`, `human_hidden_verified.json`,
`remote_connected.json`, `before_gateway_close.json`,
`gateway_closed_verified.json`, `summary.json` y la captura de Operator local
`operator_trial_complete.jpg`. Las observaciones de la Dell proceden de las
respuestas del usuario; no se afirma disponer de una captura de su pantalla.

### Defectos reales encontrados y revisión lista

Se conservaron las copias y fallos intermedios:

1. El guardia de identidad comparaba una fecha ISO con un objeto DateTime
   deserializado por PowerShell 7. Rechazó el cierre sin detener un PID ajeno.
   Ahora compara ticks UTC, conservando las validaciones de PID y comando.
2. El launcher usaba `run` tanto para una ruta como para una función asíncrona.
   La puerta podía cerrar, pero fallaba al guardar samples. Se renombró la
   función; el ensayo final sí guardó telemetría. Se añadió la regresión
   `check_launchers.py`, con servidor simulado y escritura real sin TCP.
3. Windows PowerShell 5 devolvía el array JSON de procesos como un elemento
   anidado, y Close retiró la regla/restauró el perfil sin encontrar la fila
   gateway. Una consulta conservada en `after_gateway_close.json` todavía
   mostraba el listener: **no constituye un cierre PASS**. Se solicitó entonces
   la parada independiente de la puerta mediante su archivo de control. El
   cierre real y la sesión intacta quedan en `gateway_closed_verified.json`.
   El lector emite ahora cada fila explícitamente. La regresión pasa en
   PowerShell **5.1.26100.9711** y **7.6.5**; el StopReplay final también se
   ejecutó correctamente con Windows PowerShell 5.

Los errores de lectura del sandbox y el timeout de revisión automática de una
consulta se conservaron; no acreditan fallos de red de la aplicación. Se
completaron las consultas necesarias con permisos de ejecución. El primer
`hidden_state.json` quedó sin datos por un bloqueo del sandbox y no se usa como
evidencia: `human_hidden_verified.json` contiene la verificación válida.

La consola local mantiene algunos rótulos/avisos heredados M5-C2 de ASR/DeepL y
ausencia de micrófono, pese al modo replay. Son una limitación de etiquetado
local; no prueban uso real del proveedor. Capabilities confirmó
`physical_enabled=false`, `real_deepl_enabled=false`, `translation_enabled=false`.
La laptop remota solo recibe el rótulo M5-D y el overlay permitido.

**Revisión preparada para el siguiente arranque:**

`C:/live-captions/logs/trad_lab/m5d_20261022T040503Z/environment_lan_ready_v2/plan.json`

SHA-256 `cf5105d3c530b57201b3d4726e930709573a1149fee68b600e490db91c4c869d`,
**209 archivos**. El puntero `m5d_current_plan.txt` selecciona esta revisión.
Los tres archivos de aplicación cambiados siguen siendo los mismos y las otras
192 fuentes históricas permanecen idénticas. Esta revisión agrega las
correcciones/regresiones de launcher a la app/renderer ejercitados; no se
repitió todo el ensayo físico tras el último cambio exclusivo de PowerShell.

Pruebas finales: **166 comprobaciones ASGI PASS**, 18/18 suscripciones liberadas;
regresión de launcher PASS; **nueve controles PowerShell PASS en cada versión**,
sin crear reglas o procesos en esos tests. Se conservan las 67 regresiones Python
y las suites de renderer anteriores, cuyo código protegido no cambió.

### Cierre y dictamen actualizado

`final_closure.json`, 05:05:28 UTC (01:05:28 America/La_Paz), confirma:
sin listeners en 3000/8000/8010/18000/18010, ninguna regla M5-D, cero procesos
propios de servicio y perfil Wi-Fi **Public**, igual al inicial. No se dejó un
cambio permanente de red. La señal de cierre de la puerta preservó la sesión
local antes de terminar explícitamente el replay. No se detuvo una sesión ASR.

`preservation_after_trial.json` verifica fuentes originales, 9221 archivos
históricos, `.env`, referencias Git y manifiesto final. Sin commits, tags,
merges, push, reset o releases. El error médico 90/19 y los pendientes de OBS
siguen intactos y fuera de este milestone.

La URL comprobada fue `http://10.0.0.88:3000/overlay`; **actualmente el servicio
está cerrado**. Para el próximo arranque se consulta la IP dinámica real y se
usa una red privada de confianza y la regla limitada al espectador. El flujo
con audio/ASR/DeepL reales y la integración OBS requieren sus propias pruebas.

**GO CON RESERVAS para visualización LAN del overlay en navegador: ensayo
Alienware → Dell Ubuntu aprobado dentro del alcance descrito; OBS, alpha físico
y uso real de congreso permanecen pendientes.**
