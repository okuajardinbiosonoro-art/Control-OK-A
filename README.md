# Control del Jardín Okúa

> ⚠️ **CKv1 (Legacy/Serial)**
>
> Este repositorio corresponde a la versión **CKv1** y quedó **congelado** en el release/tag **v1.0.0**.
> - Estado: **solo mantenimiento** (fixes críticos / estabilidad).
> - Desarrollo nuevo: **CKv2** → <URL_DEL_REPO_CKv2>

Aplicación de escritorio para Windows que actúa como puente **Serial -> MIDI** para la instalación interactiva Okúa.

Este README está orientado a desarrollo: explica estructura interna, flujo de datos, modelo de hilos, configuración, empaquetado y límites actuales del código.

## 1. Objetivo técnico

- Recibir bytes MIDI por puerto serial desde nodos "Maestro".
- Parsear mensajes MIDI de forma robusta en tiempo real.
- Reenviar los mensajes a puertos MIDI de salida (virtuales o físicos).
- Operar múltiples Maestros en paralelo mediante pestañas independientes.

## 2. Stack y dependencias

- Lenguaje: Python 3.10+
- GUI: `PySide6`
- Serial: `pyserial`
- MIDI: `mido` + backend `python-rtmidi`
- Build: `PyInstaller`

Archivo de dependencias: `requirements.txt`.

## 3. Estructura del proyecto

```text
Control_Okua/
├─ main.py
├─ config.json
├─ Control Okua.spec
├─ README.md
├─ requirements.txt
├─ gui/
│  ├─ main_window.py
│  ├─ maestro_tab.py
│  ├─ config_dialog.py
│  ├─ theme.qss
│  └─ __init__.py
├─ services/
│  ├─ serial_worker.py
│  └─ __init__.py
└─ assets/
   └─ icons/
      ├─ app_icon.ico
      └─ app_icon.png
```

## 4. Arquitectura interna

### 4.1 Punto de entrada

- `main.py`
- Inicializa `QApplication`.
- Resuelve rutas de recursos con `resource_path(...)` para soportar:
  - modo desarrollo (fuentes)
  - modo empaquetado (`sys._MEIPASS`, PyInstaller)
- Carga `gui/theme.qss`.
- Crea y muestra `MainWindow`.

### 4.2 Capa GUI principal

- `gui/main_window.py`
- Responsabilidades:
  - Cargar/guardar `config.json` persistente.
  - Detectar puertos MIDI disponibles por prefijo (`midi_outputs`).
  - Gestionar pestañas `MaestroTab`.
  - Mantener actividad MIDI global (msgs/seg).
  - Controlar bloqueo de puertos COM entre pestañas (`active_com_ports`).
  - Exponer acciones protegidas con PIN técnico:
    - añadir pestaña
    - editar configuración avanzada

### 4.3 Capa GUI por Maestro

- `gui/maestro_tab.py`
- Una instancia por Maestro.
- Responsabilidades:
  - Selección de puerto COM.
  - Conectar/desconectar worker por pestaña.
  - Abrir/cerrar puerto MIDI asignado a la pestaña.
  - Actualizar estado local (conectado, error, etc.).
  - Filtrar puertos COM ocupados por otras pestañas.

### 4.4 Worker serial/MIDI

- `services/serial_worker.py`
- Corre en `QThread` separado por pestaña.
- Responsabilidades:
  - Reconexión serial automática.
  - Lectura no bloqueante (`timeout=0`).
  - Parseo MIDI robusto con recuperación de desincronización.
  - Cola de mensajes MIDI y flush periódico (`flush_ms`).
  - Emisión de señales a la GUI (log, estado, actividad, puertos).

### 4.5 Configuración avanzada

- `gui/config_dialog.py`
- Editor visual de parámetros técnicos de `config.json`.
- Cambios persisten en archivo; varios requieren reinicio de app para aplicarse a todos los workers.

## 5. Modelo de concurrencia

- Cada pestaña crea su propio `QThread` y `SerialWorker`.
- La GUI nunca hace IO serial directo.
- Comunicación worker <-> GUI por señales Qt:
  - `log_signal(str, str)`
  - `status_signal(str, str)`
  - `activity_signal(int)`
  - `com_ports_signal(list)`
  - `finished()`

Patrón usado:

1. Crear `QThread`.
2. Mover `SerialWorker` al hilo (`moveToThread`).
3. Conectar señales.
4. Iniciar hilo.
5. En stop: `worker.stop()`, `thread.quit()`, `thread.wait(...)`.

## 6. Pipeline de datos Serial -> MIDI

Dentro de `SerialWorker.run()`:

1. Conecta (o reconecta) el puerto serial configurado.
2. Atiende comandos de bajada desde `command_queue` (si aplica).
3. Lee bytes disponibles (`in_waiting`) y acumula en buffer.
4. Parsea mensajes MIDI:
  - Si byte >= `0x80`: nuevo status + 2 datos.
  - Si byte < `0x80` y `running_status` habilitado: reusa último status.
  - Si mensaje inválido: descarta y avanza para resincronizar.
5. Encola mensajes válidos en `midi_queue`.
6. Cada `flush_ms`, envía cola al puerto MIDI asignado.
7. Emite actividad por segundo.
8. Si no llegan bytes en `max_silence_s`, fuerza reconexión.

## 7. Gestión de puertos

### 7.1 Puertos COM

- Se evita conectar dos pestañas al mismo COM.
- `MainWindow.request_com_port_lock(port)` otorga/rechaza lock.
- `MainWindow.release_com_port(port)` libera lock al desconectar.

### 7.2 Puertos MIDI

- Al iniciar, la app escanea salidas MIDI (`mido.get_output_names()`).
- Filtra por prefijos de `config["midi_outputs"]`.
- Cada nueva pestaña toma el primer MIDI libre del pool.
- Si no hay puertos MIDI suficientes:
  - la pestaña se desactiva para conexión.

## 8. Configuración (`config.json`)

Ubicación:

- Desarrollo: raíz del repositorio.
- EXE: carpeta donde vive el ejecutable.

Campos:

- `com_port` (`str`): puerto por defecto.
- `baudrate` (`int`): velocidad serial.
- `midi_outputs` (`list[str]`): prefijos para matching de puertos MIDI.
- `flush_ms` (`int`): ventana de flush MIDI en milisegundos.
- `max_silence_s` (`float`): umbral de silencio para reconexión.
- `running_status` (`bool`): activa parseo con running status.

Ejemplo:

```json
{
  "com_port": "COM5",
  "baudrate": 115200,
  "midi_outputs": ["loopMIDI Port"],
  "flush_ms": 10,
  "max_silence_s": 60.0,
  "running_status": false
}
```

## 9. Setup de desarrollo

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

Ejecución:

```powershell
python main.py
```

## 10. Empaquetado (PyInstaller)

Spec activo: `Control Okua.spec`.

Incluye:

- `assets/`
- `gui/theme.qss`
- hidden imports de `rtmidi`
- ícono `app_icon.ico`

Build:

```powershell
pyinstaller "Control Okua.spec"
```

Salida esperada:

- `dist/Control Okua/` (o estructura equivalente según opción de build)

## 11. Seguridad y operación

- El PIN técnico está hardcodeado en `gui/main_window.py` (`TECNICO_PIN = "0312"`).
- Para producción se recomienda mover PIN a secreto externo o variable de entorno.
- La app registra eventos en log central de GUI; no existe logging estructurado a archivo.

## 12. Limitaciones actuales

- Sin suite de tests automatizados.
- Sin validación fuerte de esquema para `config.json`.
- Sin métricas persistentes ni telemetría.
- `send_command(...)` está implementado en worker pero no expuesto por UI actual.

## 13. Checklist recomendado antes de merge

- Verificar apertura/cierre limpio de puertos COM/MIDI.
- Probar reconexión al desconectar físicamente el dispositivo serial.
- Probar `running_status=true/false` con datos reales.
- Revisar que existan al menos N puertos MIDI para N pestañas requeridas.
- Validar build de PyInstaller en entorno limpio.

## 14. Autoría

- Autor principal: **José David Pérez Zapata**
- Asistencia de desarrollo: IA (Gemini)

## 15. Licencia

Pendiente de definir. Se recomienda agregar `LICENSE` antes de publicar el repositorio.
