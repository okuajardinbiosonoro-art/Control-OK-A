# Ubicación: gui/config_dialog.py (NUEVO ARCHIVO)

import sys
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, 
                               QCheckBox, QSpinBox, QDialogButtonBox,
                               QGroupBox, QLabel)
from PySide6.QtCore import Qt

class ConfigDialog(QDialog):
    """
    Ventana de diálogo para la Configuración Avanzada.
    Permite al "Técnico" editar el config.json.
    """
    def __init__(self, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración Avanzada")
        self.setMinimumWidth(400)
        
        self.config = current_config.copy()
        
        # --- Layout Principal (Vertical) ---
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(15) # Espacio entre grupos

        # --- Texto de Advertencia (Fuera del grupo) ---
        warning_label = QLabel("Valores requieren reinicio de la app para aplicar.")
        warning_label.setStyleSheet("font-style: italic; color: #FFA726;")
        self.layout.addWidget(warning_label)

        # --- Grupo de Parámetros ---
        form_group = QGroupBox("Parámetros del Puente Serial")
        form_layout = QFormLayout()
        form_layout.setSpacing(10) # Espacio dentro del formulario
        form_group.setLayout(form_layout)
        
        # --- Widgets (Campos del formulario) ---
        self.baudrate_input = QLineEdit(str(self.config.get("baudrate", 115200)))
        
        self.flush_input = QSpinBox()
        self.flush_input.setRange(5, 100)
        self.flush_input.setValue(self.config.get("flush_ms", 15))
        self.flush_input.setSuffix(" ms")
        
        self.silence_input = QSpinBox()
        self.silence_input.setRange(100, 60000) # Rango hasta 60s
        self.silence_input.setValue(int(self.config.get("max_silence_s", 0.6) * 1000))
        self.silence_input.setSuffix(" ms")
        self.silence_input.setSingleStep(100) # Incrementar de 100 en 100

        self.rs_checkbox = QCheckBox("Habilitar Running Status (MIDI)")
        self.rs_checkbox.setChecked(self.config.get("running_status", True))
        
        # --- Añadir widgets al formulario ---
        form_layout.addRow("Baudrate:", self.baudrate_input)
        form_layout.addRow("Ventana de Envío (Flush):", self.flush_input)
        form_layout.addRow("Tiempo de Reconexión (Silence):", self.silence_input)
        form_layout.addRow("", self.rs_checkbox)

        # --- Botones OK/Cancelar ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                           QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # --- Ensamblar Layout ---
        self.layout.addWidget(form_group)
        self.layout.addWidget(self.button_box)

    def get_config(self):
        """
        Lee los valores de los widgets y los devuelve
        en el formato de config.json.
        """
        self.config["baudrate"] = int(self.baudrate_input.text())
        self.config["flush_ms"] = self.flush_input.value()
        self.config["max_silence_s"] = self.silence_input.value() / 1000.0
        self.config["running_status"] = self.rs_checkbox.isChecked()
        
        return self.config