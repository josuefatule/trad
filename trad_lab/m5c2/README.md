# M5-C2 A — ensayo físico experimental

El ensayo A falló antes del primer PCM por usar `.venv` para TRAD: el import
diferido `flow → transport → adapter` requiere NumPy. No se instalaron paquetes.
Las regresiones y los controles en memoria usaron `.venv-wlk`; ambos servicios
deben usar ese entorno existente en una ejecución futura revisada.

`serve.preflight_dependencies()` comprueba ese import antes de cargar el modelo
o abrir TCP. Esta corrección está solo en las fuentes nuevas del laboratorio;
no modifica la copia ejecutada ni autoriza otro ensayo. Para repetir se debe
crear y verificar una copia nueva y obtener revisión/autorización humana.

En la futura copia, desde su `copy/`, los comandos revisados utilizarán ambos:

```powershell
& 'C:\live-captions\.venv-wlk\Scripts\python.exe' -m trad_lab.m5c2.serve backend --plan RUTA_PLAN_NUEVO --authorization 'M5-C2 A ASR físico autorizado'
& 'C:\live-captions\.venv-wlk\Scripts\python.exe' -m trad_lab.m5c2.serve trad --plan RUTA_PLAN_NUEVO --authorization 'M5-C2 A ASR físico autorizado'
```

No ejecutar con la copia histórica fallida: su runtime se conserva y el launcher
rechaza reutilizarlo. DeepL, OBS real y fase B siguen pendientes de aprobación.
El FIR127 y el perfil Turbo permanecen sin cambios. No hay fallback automático.
