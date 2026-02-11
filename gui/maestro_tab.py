# Ubicación: gui/maestro_tab.py

import sys
import mido
import serial
import serial.tools.list_ports
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QComboBox, QGroupBox,
                               QLabel)
from PySide6.QtCore import QThread, Signal, QObject

from services.serial_worker import SerialWorker

STATUS_COLORS = {
    "red": "#E57373",
    "green": "#2FACC6",
    "orange": "#FFA726",
    "blue": "#4FC3F7",
    "gray": "#AAAAAA"
}

class MaestroTab(QWidget):
    """
    Este widget es la "plantilla" para una sola pestaña de Maestro.
    """
    
    log_signal = Signal(str, str)
    activity_signal = Signal(int)
    port_released_signal = Signal(str) 

    # ¡CAMBIO! Se ha añadido parent_window
    def __init__(self, parent_window, config, assigned_midi_port_name, tab_index):
        super().__init__()
        
        self.parent_window = parent_window # Referencia a la GUI principal
        self.config = config
        self.tab_index = tab_index
        
        self.assigned_midi_port_name = assigned_midi_port_name
        self.midi_output_port = None
        
        self.worker_thread = None
        self.worker = None

        self.init_ui()
        self.connect_signals()
        
        # --- ¡NUEVO! Guardia de Protección MIDI [Req 1] ---
        if not self.assigned_midi_port_name:
             self.log_signal.emit(f"[Pestaña {self.tab_index}] ¡Advertencia! No hay puerto MIDI disponible. Conexión desactivada.", "orange")
             self.btn_connect.setEnabled(False)
             self.btn_connect.setText("MIDI No Detectado")
             self.btn_refresh_coms.setEnabled(False)
             self.combo_com_ports.setEnabled(False)
             self.update_status("Desactivado", "gray")
        
        self.btn_refresh_coms.clicked.emit()

    def init_ui(self):
        """Crea la interfaz gráfica para esta pestaña"""
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 15, 10, 10)

        conn_layout = QHBoxLayout()
        
        conn_layout.addWidget(QLabel("Maestro:"))
        self.combo_com_ports = QComboBox()
        self.btn_refresh_coms = QPushButton("Refrescar")
        self.btn_connect = QPushButton("Conectar")
        self.btn_connect.setCheckable(True)
        self.label_status_light = QLabel("●")
        self.label_status_text = QLabel("Desconectado")
        self.update_status("Desconectado", "red")

        conn_layout.addWidget(self.combo_com_ports)
        conn_layout.addWidget(self.btn_refresh_coms)
        conn_layout.addWidget(self.btn_connect)
        conn_layout.addWidget(self.label_status_light)
        conn_layout.addWidget(self.label_status_text)
        conn_layout.addStretch()
        
        main_layout.addLayout(conn_layout)
        main_layout.addStretch() 
        
    def connect_signals(self):
        self.btn_refresh_coms.clicked.connect(self.on_refresh_coms)
        self.btn_connect.clicked.connect(self.on_connect_toggle)

    # --- ¡NUEVO! Función helper ---
    def get_current_com_port(self):
        return self.combo_com_ports.currentText()

    # --- SLOTS (Funciones de la GUI) ---

    def on_refresh_coms(self):
        self.log_signal.emit("Escaneando puertos COM...", "gray")
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.update_com_ports(ports)
    
    def on_connect_toggle(self, checked):
        """Maneja el clic en "Conectar" / "Desconectar" """
        selected_port = self.combo_com_ports.currentText()

        if checked:
            # --- CONECTAR ---
            if not selected_port:
                self.log_signal.emit("Error: No hay ningún puerto COM seleccionado.", "red")
                self.btn_connect.setChecked(False)
                return

            # --- ¡NUEVO! Guardia de Protección COM [Req 2] ---
            if not self.parent_window.request_com_port_lock(selected_port):
                self.log_signal.emit(f"Error: El puerto {selected_port} ya está en uso en otra pestaña.", "red")
                self.btn_connect.setChecked(False) # Revertir el clic
                return
            # --- Fin de la Guardia ---

            if self.assigned_midi_port_name and not self.midi_output_port:
                try:
                    self.midi_output_port = mido.open_output(self.assigned_midi_port_name)
                    self.log_signal.emit(
                        f"Pestaña {self.tab_index}: Puerto MIDI '{self.assigned_midi_port_name}' asignado y abierto.",
                        "green"
                    )
                except Exception as e:
                    # No tiene sentido mantener la conexión Serial si no hay salida MIDI.
                    self.log_signal.emit(
                        f"Pestaña {self.tab_index}: ¡Error al abrir el puerto MIDI '{self.assigned_midi_port_name}'! {e}",
                        "red"
                    )
                    self.midi_output_port = None

                    # Liberar inmediatamente el COM que habíamos bloqueado
                    self.parent_window.release_com_port(selected_port)

                    # Revertir estado del botón y de la UI
                    self.btn_connect.setChecked(False)
                    self.btn_connect.setText("Conectar")
                    self.combo_com_ports.setEnabled(True)
                    self.btn_refresh_coms.setEnabled(True)
                    self.update_status("Error MIDI", "red")
                    return  # No arrancamos el worker
            
            thread_config = self.config.copy()
            thread_config["com_port"] = selected_port
            
            self.log_signal.emit(f"Iniciando conexión a {selected_port}...", "blue")
            
            self.worker_thread = QThread()
            self.worker = SerialWorker(thread_config, self.midi_output_port) 
            self.worker.moveToThread(self.worker_thread)
            
            self.worker.log_signal.connect(self.log_signal)
            self.worker.status_signal.connect(self.update_status)
            self.worker.activity_signal.connect(self.activity_signal)
            self.worker.com_ports_signal.connect(self.update_com_ports)
            self.worker.finished.connect(self.worker_thread.quit)
            
            self.worker_thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker_thread.finished.connect(self.worker_thread.deleteLater)
            
            self.worker_thread.start()
            
            self.btn_connect.setText("Desconectar")
            self.combo_com_ports.setEnabled(False)
            self.btn_refresh_coms.setEnabled(False)

        else:
            # --- DESCONECTAR ---
            self.log_signal.emit(f"Desconectando de {selected_port}...", "gray")
            
            if self.worker:
                self.worker.stop()
            
            if self.midi_output_port:
                self.log_signal.emit(f"Pestaña {self.tab_index}: Liberando puerto '{self.midi_output_port.name}'.", "gray")
                self.midi_output_port.close()
                self.midi_output_port = None

            # --- ¡NUEVO! Liberar el puerto COM [Req 2] ---
            self.parent_window.release_com_port(selected_port)

            self.btn_connect.setText("Conectar")
            self.update_status("Desconectado", "red")
            self.combo_com_ports.setEnabled(True)
            self.btn_refresh_coms.setEnabled(True)

    def update_status(self, text, color_name):
        """Actualiza el indicador de estado de ESTA pestaña"""
        self.label_status_text.setText(text)
        hex_color = STATUS_COLORS.get(color_name, "black")
        self.label_status_light.setStyleSheet(f"color: {hex_color}; font-weight: bold;")

    def update_com_ports(self, ports):
        """Actualiza la lista del menú desplegable COM"""
        current = self.combo_com_ports.currentText()
        self.combo_com_ports.clear()
        
        # Filtrar puertos que ya están en uso por otras pestañas
        available_ports_for_this_tab = [p for p in ports if p not in self.parent_window.active_com_ports or p == current]
        self.combo_com_ports.addItems(available_ports_for_this_tab)
        
        if current in available_ports_for_this_tab:
            self.combo_com_ports.setCurrentText(current)
        
    def stop_worker(self):
        """Función llamada por la ventana principal al cerrar."""
        # Liberar el puerto COM si estaba conectado
        if self.btn_connect.isChecked():
            self.parent_window.release_com_port(self.get_current_com_port())
        
        if self.worker:
            self.worker.stop()
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait(500)
            
        if self.midi_output_port:
            self.midi_output_port.close()
            self.port_released_signal.emit(self.assigned_midi_port_name)