# Código reutilizado

`app/static/pcm_worklet.js` y `app/static/recorder_worker.js` se basan en los archivos
homónimos de WhisperLiveKit 0.2.26 instalado localmente. Licencia Apache 2.0:
`WhisperLiveKit-LICENSE.txt`.

Cambios locales: señal de barrera `flush` para drenar mensajes pendientes antes
del frame de fin de audio. Se conserva el algoritmo original de muestras y PCM.
