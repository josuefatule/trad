# Auditoría previa M7 — 2026-10-17

Base M6 `0d4eb6c`. Configuración A, normalización, glosarios y modelo ASR se conservan.

| Fallo | M6 existente | Decisión M7 |
| --- | --- | --- |
| WLK no disponible al arrancar | Error inmediato; timeout de conexión | Reintentos limitados antes de PCM, backoff/jitter/cancelación |
| WLK se pierde durante LIVE | Cancela relay y limpia overlay; nueva sesión manual | No reanudar un AudioProcessor nuevo con estado antiguo; informar final incompleto y pérdidas pendientes |
| Refresh de Operator | Destruye AudioContext/socket, cancela la sesión; nonce solo en memoria | Captura separada; recuperación autenticada de consola y lease exclusiva |
| Propietario desaparecido | Nonce inaccesible, sin transferencia | Heartbeat del controlador, recuperación con secreto de la pestaña o credencial administrativa local |
| Overlay desconectado | Backoff exponencial sin límite/jitter; snapshot v3 y CLEAR correctos | Mantener v3, añadir límites/jitter/cancelación y diagnóstico |
| Micrófono no produce PCM | Track ended detectado; no supervisión de frames | Medir frames/bytes recibidos; silencio con PCM no es fallo |
| ASR abierto pero inactivo | Se observan mensajes, sin watchdog | Separar mensajes ASR de progreso textual y silencio; timestamps y degradación explicada |
| DeepL temporal/429/timeout | Retry inmediato para cualquier error | Clasificación, backoff limitado, deadline/caducidad y riesgo de consumo duplicado |
| DeepL auth/cuota | Repite en cada segmento | Circuito permanente; intervención/rearme explícito |
| STOP con proveedor bloqueado | Timeout de WLK existente; drain de traducción acotado indirectamente | Plazo total explícito, pendientes cuantificados, resultado incompleto |
| Saturación | Cola 32 y errores ordenados; buffer completed puede crecer en ráfagas | Presupuesto de sesión y backpressure auditable, nunca éxito ficticio |
| Sesión larga | Historial WLK/full, manager, UI y memo crecen; logs rotan | Presupuesto de duración/tamaño y retención UI/eventos acotada con contadores |
| Logs | Rotación existente; eventos manager incluyen texto por defecto | Proyección estructurada sin texto ni secretos por defecto |

Puntos únicos de fallo: proceso FastAPI/memoria del hub, proceso WLK/GPU externo,
ventana que posee el micrófono, acceso a Internet/DeepL. No se añadirá persistencia
que permita fingir continuidad después de reiniciar esos procesos. No se reiniciarán
procesos externos automáticamente ni durante sesiones activas.

Baseline y resultados finales, incluidos los 24 escenarios obligatorios, se
registran en [M7_REPORT.md](M7_REPORT.md). Procedimientos y límites implementados
en [RELIABILITY_RUNBOOK.md](RELIABILITY_RUNBOOK.md).
