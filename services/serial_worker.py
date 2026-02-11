import sys
import time
import queue
import serial
import serial.tools.list_ports
import mido
from PySide6.QtCore import QThread, Signal, QObject, Slot 

class SerialWorker(QObject):
    """
    Worker de HILO ÚNICO (v3.2 - Asignación de Puerto Único).
    Maneja LECTURA y ESCRITURA en un hilo.
    Ahora envía MIDI a un solo puerto asignado.
    """
    log_signal = Signal(str, str)
    status_signal = Signal(str, str)
    activity_signal = Signal(int)
    com_ports_signal = Signal(list)
    finished = Signal()

    def __init__(self, config, midi_output_port): # <-- CAMBIO: Ya no es una lista
        super().__init__()
        
        self.config = config
        self.midi_output_port = midi_output_port # <-- CAMBIO: Almacena el puerto único
        
        self.running = False
        self.ser = None
        self.command_queue = queue.Queue()

    def stop(self):
        self.running = False
        # Enviar None a la cola para despertar al hilo de escritura (si está bloqueado)
        # (Aunque nuestro hilo de escritura ya no se bloquea, es una buena práctica)
        self.command_queue.put(None) 

    @Slot(int, int, int)
    def send_command(self, node_id, mode, palette):
        cmd = f"C,{node_id},{mode},{palette}\n"
        self.command_queue.put(cmd)

    def scan_com_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.com_ports_signal.emit(ports)

    def run(self):
        """
        El Loop Principal del Worker.
        """
        self.running = True
        self.log_signal.emit(f"Iniciando worker para {self.config['com_port']}", "gray")

        buf = bytearray()
        rs_status = None
        last_byte_time = time.time()
        midi_msg_count = 0
        last_stat_time = time.time()
        
        midi_queue = queue.Queue()
        flush_window_s = self.config['flush_ms'] / 1000.0
        last_flush_time = time.time()

        while self.running:
            try:
                # --- 1. Intento de Conexión / Reconexión ---
                if self.ser is None or not self.ser.is_open:
                    if self.running:
                        self.status_signal.emit(f"Reconectando...", "orange")
                        self.log_signal.emit(f"Intentando conectar a {self.config['com_port']}...", "orange")
                        try:
                            self.ser = serial.Serial(self.config['com_port'], 
                                                     self.config['baudrate'], 
                                                     timeout=0) # NO BLOQUEANTE
                            self.status_signal.emit("Conectado", "green")
                            self.log_signal.emit(f"¡Éxito! Conectado a {self.config['com_port']}.", "green")
                            last_byte_time = time.time()
                        except serial.SerialException as e:
                            self.status_signal.emit("Error de Puerto", "red")
                            self.log_signal.emit(f"Error al abrir {self.config['com_port']}: {e}", "red")
                            time.sleep(2)
                            continue
                
                # --- 2. Vía de Bajada (Enviar Comandos) ---
                while not self.command_queue.empty():
                    cmd = self.command_queue.get()
                    if cmd is None:
                        self.running = False
                        break
                    self.ser.write(cmd.encode('ascii'))
                    self.log_signal.emit(f"Comando enviado al Maestro: {cmd.strip()}", "blue")

                if not self.running:
                    continue

                # --- 3. Vía de Subida (Leer MIDI) ---
                bytes_to_read = self.ser.in_waiting
                if bytes_to_read > 0:
                    chunk = self.ser.read(bytes_to_read)
                    last_byte_time = time.time()
                    buf.extend(chunk)

                # --- 4. Parseo MIDI (robusto frente a basura) ---
                processed = 0
                # Necesitamos al menos 3 bytes para intentar un mensaje completo
                while len(buf) - processed >= 3:
                    b0 = buf[processed]

                    if b0 & 0x80:
                        # Nuevo STATUS: asumimos mensaje de 3 bytes (status + 2 datos)
                        status, d1, d2 = buf[processed : processed + 3]
                        bytes_consumidos = 3
                        rs_status = status
                    else:
                        # Byte de datos: solo tiene sentido si hay running status activo
                        if not self.config['running_status'] or rs_status is None:
                            # No hay STATUS previo válido: descartamos este byte y seguimos
                            processed += 1
                            continue
                        status = rs_status
                        d1, d2 = buf[processed : processed + 2]
                        bytes_consumidos = 2

                    # Intentar construir el mensaje MIDI de forma segura
                    try:
                        msg = mido.Message.from_bytes([status, d1, d2])
                    except ValueError as e:
                        # Estos bytes NO forman un mensaje MIDI válido.
                        # Importante: avanzar para no quedarnos pegados en los mismos datos.
                        self.log_signal.emit(
                            f"Advertencia: mensaje MIDI inválido descartado "
                            f"([{status}, {d1}, {d2}]): {e}",
                            "orange"
                        )
                        # Avanzamos solo un byte para intentar resincronizar el flujo
                        processed += 1
                        # Opcional: olvidamos el running status para empezar limpio
                        rs_status = None
                        continue

                    # Si llegamos aquí, el mensaje es válido
                    midi_queue.put(msg)
                    midi_msg_count += 1
                    processed += bytes_consumidos

                if processed > 0:
                    del buf[:processed]

                # --- 5. Flusher MIDI ---
                # ¡CAMBIO! Solo enviar si tenemos un puerto asignado
                if self.midi_output_port and (time.time() - last_flush_time > flush_window_s):
                    while not midi_queue.empty():
                        msg_to_send = midi_queue.get()
                        try:
                            self.midi_output_port.send(msg_to_send)
                        except Exception as e:
                            self.log_signal.emit(f"Error al enviar a MIDI ({self.midi_output_port.name}): {e}", "red")
                    last_flush_time = time.time()

                # --- 6. Indicador de Actividad ---
                if time.time() - last_stat_time > 1.0:
                    msgs_per_sec = midi_msg_count
                    self.activity_signal.emit(msgs_per_sec) # Emitir la actividad de esta pestaña
                    midi_msg_count = 0
                    last_stat_time = time.time()

                # --- 7. Reconexión Automática ---
                if time.time() - last_byte_time > self.config['max_silence_s']:
                    self.log_signal.emit(f"Silencio detectado ({self.config['max_silence_s']}s). Reconectando...", "orange")
                    self.ser.close()
                    last_byte_time = time.time()

            except serial.SerialException as e:
                self.log_signal.emit(
                    f"¡Error Crítico! Puerto {self.config['com_port']} desconectado. {e}",
                    "red"
                )
                self.status_signal.emit("Error de Puerto", "red")
                if self.ser:
                    self.ser.close()
                self.ser = None
                time.sleep(1)
            
            except Exception as e:
                # Aquí deberían llegar SOLO errores realmente inesperados,
                # no errores de bytes MIDI sueltos.
                self.log_signal.emit(f"Error inesperado en worker: {e}", "red")
                time.sleep(1)
            
            time.sleep(0.001) 
    
        # --- Limpieza al salir del loop ---
        self.log_signal.emit("Deteniendo worker...", "gray")
        self.finished.emit()
        
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.status_signal.emit("Desconectado", "red")
        self.activity_signal.emit(0)
