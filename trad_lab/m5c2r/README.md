# M5-C2 B — revisión del registrador y de presentación

Solo copia experimental. Turbo, perfil M5-A/M5-B2, FIR, crédito, autenticación,
TranscriptState, SegmentManager y proveedor DeepL no se cambian.

El registrador envía paquetes autenticados durante la sesión: cola de 8 MiB
incluido el paquete pendiente, ACK de escritura de cinco segundos, sin retry.
Libera los registros escritos. El writer conserva su máximo de 160 MiB;
al llegar a 128 MiB escritos se solicita un cierre controlado con diagnóstico
incompleto y margen para drenar. Un fallo del registro no lanza excepciones
desde el callback: solicita flush/EOF, conserva los créditos y no declara
`experiment_complete` si falta evidencia. La recuperación del propietario
usa el token actual; espera hasta cinco segundos mientras se recarga Operator,
sin usar un token antiguo ni reintentar un rechazo HTTP.

La copia selecciona `timed_queue`, paginación ya existente del renderer.
No recorta el principio de un caption largo como el scroll del ensayo B.
Conserva fuente, geometría, límites de cola/backlog y tiempos de lectura.
Overflow, caducidad o texto ilegible suspenden la presentación y muestran aviso;
requieren revisión y CLEAR/decisión del operador. El journal conserva el texto.
No se afirma que los mensajes ocultados intencionalmente por CLEAR/OCULTAR deban
mostrarse de nuevo. La cola visual agrega espera; fidelidad prima sobre latencia.

Las pruebas son en memoria, con APIs nativas sintéticas, o Chrome headless
por `file://`. Ninguna abre micrófono, modelo, DeepL real, OBS o servicios TCP.

Para repetir B se necesita presencia del usuario, copia congelada nueva, Chrome
nuevo y fuente OBS experimental inicialmente oculta. Verificar ambos servidores
con `.venv-wlk` y el plan aprobado, nunca arrancar desde LIVE. `serve` utiliza
el interlock histórico `M5-C2 B DeepL OBS autorizado`; la autorización humana
se registra aparte. Mantener tramo corto conocido, controles supervisados,
STOP/EOF, `experiment_complete=true`, evidencia sellada y cola OBS drenada antes
de cerrar servicios. Ante un fallo no reiniciar automáticamente.

Rollback: cerrar solo la copia tras drenaje o fallo explícito, ocultar la fuente
experimental y conservar evidencias. LIVE no requiere restauración. No volver
automáticamente a la revisión B que falló.
