# M5 — validación del overlay, 2026-10-16

Baseline: 103 pruebas Python pasaban antes de M5. La configuración automática de
DeepL/.env pendiente quedó registrada como commit M4.1 separado del overlay.

Validación M5:

- 116 pruebas Python: PASS (13 nuevas de hub, rutas e integración).
- Pruebas DOM Operator y overlay: PASS mediante runtime Node disponible en Codex.
- Sintaxis de todos los JavaScript: PASS con vm.Script.
- Renderer con reloj controlado: wrapping, preservación de palabras, Unicode,
  paginación, tokens largos, expiración, STOP, reset, desconexión, reconexión,
  saturación, inyección HTML y eventos stale: PASS.
- compileall y git diff --check: PASS.
- Integración FastAPI → WLK simulado → normalizador → provider controlado → Operator
  + dos overlays: PASS; una conexión WLK, una traducción, dos entregas idénticas.
- Cierre de Operator durante captura: disconnected recibido por overlay; una
  segunda sesión concurrente se rechaza sin reemplazar la sesión activa.

Replay del fixture médico con mock explícito, sin servidores ni DeepL:

```text
segments=16 late_revisions=0 integrity=PASS source_words=81 emitted_words=81
translation_successes=16 translation_failures=0 retries=0 timeouts=0
```

La salida mock sirve para regresión M4 y se filtra por completo en el overlay de
producción. La demo M5 usa fixtures ingleses independientes y muestra DEMO de forma
permanente; no usa el provider mock ni el hub de producción.

La inspección visual en Chrome no se completó: el control de navegador se detuvo
al no poder identificar con confianza la URL actual. No se instaló ni modificó OBS.
Queda pendiente verificar composición/transparencia visual en OBS y lectura real
con Blue Yeti + DeepL. La transparencia de html/body se verifica en CSS y rutas;
la asignación textContent y la política temporal se verifican ejecutando el JS real.

Los thresholds visuales iniciales son 2 líneas, Arial 48 px, ancho 1500 px, margen
inferior 70 px, fondo negro .72, lectura 3 palabras/s con 1800–6500 ms por bloque.
Cola visual: 64 bloques / 20 s de atraso; saturación se descarta y cuenta
explícitamente. Hub: 32 observadores / 64 eventos cada uno / timeout envío 2 s.
No se promete delivery completo durante desconexiones o sobrecarga.

No se modificaron Whisper, reconciliación, thresholds de SegmentManager, glosarios,
normalización, modelo de datos TranslationResult ni motor DeepL durante M5.
