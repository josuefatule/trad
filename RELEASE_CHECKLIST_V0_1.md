# Checklist de release v0.1

Estados: **AUTOMÁTICO**, **MANUAL**, **PENDIENTE**, **BLOQUEADO**. Una casilla sin
marcar no se interpreta como PASS. Base M7: `6b4d729`. Candidato: tag local
`v0.1.0-rc1` tras los gates automáticos. Final `v0.1.0`: no autorizado todavía.

## Gates del candidato técnico

- [x] Auditoría de Git limpio y docs M1–M7; no sobrescribir cambios del usuario.
- [x] Configuración A, WLK, normalización, glosarios, DeepLProvider, Hub y rolling preservados.
- [x] Python 3.12.10 y dependencias observadas inventariadas; pip check PASS.
- [x] Seis suites JS baseline PASS; Python baseline 175 PASS con hora virtual incluida.
- [x] Regresión final completa M1–M8: 180 Python PASS, seis suites JS PASS, sin skips de navegador.
- [x] Replay A: integridad RAW 81/81, cero pérdida/duplicación/late revisions.
- [x] E2E fixture/Chrome con CAPTURE, CLEAR, reload/reconnect, dos STOP completos y aislamiento.
- [x] Timestamps monotónicos correlacionados por sesión/segmento; relojes y desconocidos explícitos.
- [x] Latencias n/mediana/p90/p95/máximo, cola, tasa y trayectoria documentadas.
- [x] Calidad lingüística y errores de significado documentados; sin métricas inventadas.
- [x] Seguridad local, Host/Origin/nonce/owner, overlay readonly, secretos/logs revisados.
- [x] `.env.example` sin clave y traducción inicialmente deshabilitada.
- [x] Instalación/cierre/recuperación/rollback y configuración OBS documentados.
- [x] Hora virtual M7 repetida con JSON de métricas M8 y cleanup PASS.
- [x] Commit M8 y tag RC local preparados con gates automáticos PASS; verificar
  `git rev-parse v0.1.0-rc1^{commit}` y `git status --short` tras crear el candidato.

## Gates de aceptación final (no sustituidos por simulación)

- [x] **MANUAL informado por usuario:** M7 con Blue Yeti, WLK, DeepL, Operator,
  CAPTURE, OBS, START/STOP/CLEAR, reload/recovery y continuidad/aislamiento.
- [ ] **PENDIENTE:** nueva lectura M8 de todos los pasos 1–19 y acta firmada/confirmada.
- [ ] **PENDIENTE:** 60–90 minutos reales supervisados, cuota autorizada y métricas completas.
- [ ] **PENDIENTE:** voz→proyección con un reloj audiovisual, o aceptación explícita
  de esa medición como limitación; no convertir paint en latencia física.
- [ ] **PENDIENTE:** revisión de inglés médico, negaciones, dosis, unidades, lateralidad,
  fármacos y riesgos de omisión/duplicación conocidos. Bloquear si no se aceptan.
- [ ] **PENDIENTE:** instalación limpia Windows/ASR/GPU y smoke test con pins documentados.
- [ ] **PENDIENTE:** OBS/proyector físico, dos/tres líneas sin clipping y aspecto de diapositivas.
- [ ] **PENDIENTE:** memoria/CPU/GPU/colas/errores/consumo/inicio-final/STOP revisados.
- [ ] **PENDIENTE:** autorización explícita del usuario para tag final `v0.1.0`.

Si un gate no puede ejecutarse por una causa concreta, cambiar su estado a
**BLOQUEADO**, anotar causa, fecha, responsable y acción necesaria. Hoy la aceptación
física está pendiente de ejecución; no hay evidencia para declararla aprobada.

## Operación mínima y riesgos aceptables por revisar

Arranque: WLK listo → FastAPI un worker loopback → Operator/OBS actualizados →
selección Blue Yeti → START/CAPTURE → comprobar resultado DeepL real. STOP → flush/
drain complete y cola 0 → cerrar CAPTURE → Ctrl+C servidores. CLEAR solo es visual.

Recuperación: recargar Operator conserva CAPTURE/session_id; overlay restaura
snapshot vigente/generación; pérdida de WLK/CAPTURE durante LIVE exige sesión nueva.
No reiniciar procesos en LIVE, no recuperar audio inexistente, no duplicar workers.
Los historiales y métricas son acotados y se pierden al reiniciar. Ver
[RELIABILITY_RUNBOOK.md](RELIABILITY_RUNBOOK.md).

Limitaciones: PARTIAL WLK vacío; latencia ASR→READY dominante y poll Operator de 2 s;
cortes de unidades médicas y errores ingleses históricos; retries potencialmente
facturables; presupuesto de sesión 2 h y límites ASR/READY; ausencia de persistencia;
instalación CUDA limpia no demostrada; telemetría de navegador no equivale a OBS físico.

Evidencia: [VALIDATION_REPORT_V0_1.md](VALIDATION_REPORT_V0_1.md),
[LATENCY_BASELINE_V0_1.md](LATENCY_BASELINE_V0_1.md),
[MANUAL_VALIDATION_V0_1.md](MANUAL_VALIDATION_V0_1.md),
[INSTALL_WINDOWS.md](INSTALL_WINDOWS.md).
