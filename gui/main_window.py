# Ubicación: gui/main_window.py

import sys
import os # <-- ¡AÑADIDO!
import json
import mido
import serial
import serial.tools.list_ports
from PySide6.QtWidgets import (QMainWindow, QApplication, QWidget, QVBoxLayout, 
                               QTabWidget, QGroupBox, QLabel, QTextEdit, 
                               QStatusBar, QPushButton, QInputDialog, QLineEdit,
                               QMessageBox)
from PySide6.QtCore import Signal, Qt, Slot
from PySide6.QtGui import QAction

from gui.maestro_tab import MaestroTab
from gui.config_dialog import ConfigDialog

# --- ¡NUEVA FUNCIÓN DE AYUDA! ---
def resource_path(relative_path):
    """ Obtiene la ruta absoluta al recurso, funciona para dev y para PyInstaller """
    try:
        # PyInstaller crea una carpeta temporal y guarda la ruta en _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # No estamos empaquetados, la ruta es la del script (gui/)
        # así que subimos un nivel a la raíz del proyecto (Control_Okua)
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return os.path.join(base_path, relative_path)
# --- FIN DE LA FUNCIÓN DE AYUDA ---

# --- Helpers de rutas para config ------------------------------------------

def get_project_root():
    """
    Devuelve la carpeta base del proyecto:
    - En desarrollo: raíz del repo (CONTROL_OKUA).
    - En exe (PyInstaller): carpeta donde vive Control Okúa.exe.
    """
    if getattr(sys, "frozen", False):
        # Ejecutado como .exe
        return os.path.dirname(sys.executable)
    else:
        # Ejecutado desde código fuente -> subir desde gui/ a la raíz
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_config_path():
    """Ruta PERSISTENTE para config.json."""
    return os.path.join(get_project_root(), "config.json")


STATUS_COLORS = {
    "red": "#E57373",
    "green": "#2FACC6",
    "orange": "#FFA726",
    "blue": "#4FC3F7",
    "gray": "#AAAAAA"
}

TECNICO_PIN = "0312"

class MainWindow(QMainWindow):
    """
    Ventana Principal de la GUI (v1.9 - Empaquetado de Recursos)
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Control del Jardín Okúa v1.0")
        self.setMinimumSize(700, 500)

        self.load_config()
        self.available_midi_port_names = self.scan_midi_port_names()
        
        self.maestro_tabs = []
        self.activity_counters = {}
        self.active_com_ports = set()

        self.init_ui()
        self.init_menu()
        self.connect_signals()
        
        self.add_maestro_tab()
        self.add_maestro_tab()

    def load_config(self):
        """Carga el config.json (persistente)."""
        try:
            config_path = get_config_path()
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"No se pudo cargar config.json ({e}). Usando defaults.")
            self.config = {
                "com_port": "",
                "baudrate": 115200,
                "midi_outputs": ["loopMIDI"],
                "flush_ms": 15,
                "max_silence_s": 60.0,   # coherente con tu config.json actual
                "running_status": True,
            }

    def scan_midi_port_names(self):
        """Escanea y devuelve una lista de nombres de puertos MIDI"""
        available_ports = mido.get_output_names()
        found_ports = []
        config_prefixes = self.config.get("midi_outputs", ["loopMIDI"])
        
        for prefix in config_prefixes:
            for real_port in available_ports:
                if prefix in real_port:
                    found_ports.append(real_port)
        
        if len(found_ports) < 2:
             print(f"¡ADVERTENCIA! Se encontraron menos de 2 puertos MIDI ({len(found_ports)}).")
        
        print(f"Puertos MIDI disponibles encontrados: {found_ports}")
        return found_ports

    def init_ui(self):
        """Crea la interfaz gráfica principal con pestañas"""
        
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        self.setCentralWidget(main_widget)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        
        log_group = QGroupBox("Log de Actividad Central")
        log_layout = QVBoxLayout()
        log_group.setLayout(log_layout)
        
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        log_layout.addWidget(self.log_box)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.label_midi_activity = QLabel("Actividad MIDI Global: 0 msgs/seg")
        self.status_bar.addPermanentWidget(self.label_midi_activity)

        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(log_group, stretch=1)
    
    def init_menu(self):
        """Crea la Barra de Menú superior"""
        menu_bar = self.menuBar()
        
        archivo_menu = menu_bar.addMenu("Archivo")
        quit_action = QAction("Salir", self)
        quit_action.triggered.connect(self.close)
        archivo_menu.addAction(quit_action)

        avanzado_menu = menu_bar.addMenu("Avanzado")
        
        self.action_add_tab = QAction("Añadir Pestaña de Maestro", self)
        self.action_add_tab.triggered.connect(self.prompt_for_pin_and_add_tab)
        avanzado_menu.addAction(self.action_add_tab)
        
        avanzado_menu.addSeparator()

        self.action_config = QAction("Editar Configuración...", self)
        self.action_config.triggered.connect(self.prompt_for_pin_and_open_config)
        avanzado_menu.addAction(self.action_config)
        
        ayuda_menu = menu_bar.addMenu("Ayuda")
        self.action_about = QAction("Acerca de...", self)
        self.action_about.triggered.connect(self.show_about_dialog)
        ayuda_menu.addAction(self.action_about)


    def connect_signals(self):
        """Conecta las señales del sistema de pestañas."""
        self.tab_widget.tabCloseRequested.connect(self.close_maestro_tab)

    def add_maestro_tab(self):
        """Crea una nueva pestaña de Maestro y le asigna un puerto MIDI."""
        
        assigned_port_name = None
        if self.available_midi_port_names:
            assigned_port_name = self.available_midi_port_names.pop(0)
        else:
            self.update_log("¡ERROR! No hay más puertos MIDI disponibles para asignar.", "red")
            
        tab_index = self.tab_widget.count()
        new_tab = MaestroTab(self, self.config, assigned_port_name, tab_index + 1)
        self.maestro_tabs.append(new_tab)
        
        new_tab.log_signal.connect(self.update_log)
        new_tab.activity_signal.connect(
            lambda activity, tab=new_tab: self.update_global_midi_activity(tab, activity)
        )
        new_tab.port_released_signal.connect(self.release_midi_port)
        
        tab_name = f"Maestro {len(self.maestro_tabs)}"
        self.tab_widget.addTab(new_tab, tab_name)
        self.tab_widget.setCurrentWidget(new_tab)
        
        self.activity_counters[new_tab] = 0

    def close_maestro_tab(self, index):
        """Cierra una pestaña y detiene su hilo de forma segura."""
        
        if self.tab_widget.count() <= 2:
            self.update_log("Error: No se pueden cerrar las pestañas base (se requiere un mínimo de 2).", "red")
            return

        tab_to_close = self.tab_widget.widget(index)
        if tab_to_close:
            self.update_log(f"Cerrando pestaña {self.tab_widget.tabText(index)}...", "gray")
            tab_to_close.stop_worker()
            
            if tab_to_close in self.maestro_tabs:
                self.maestro_tabs.remove(tab_to_close)
            
            self.tab_widget.removeTab(index)
            tab_to_close.deleteLater()
            
            if tab_to_close in self.activity_counters:
                del self.activity_counters[tab_to_close]
            self.recalculate_global_activity()

    def show_about_dialog(self):
        """Muestra la ventana emergente 'Acerca de'."""
        info_texto = """
        <b>Control del Jardín Okúa v1.0</b>
        <p>Esta aplicación sirve como puente de monitoreo Serial-MIDI 
        para la instalación interactiva Okúa.</p>
        <p>Maneja la recepción de datos de los Maestros (audio) y 
        la gestión de la configuración avanzada del sistema.</p>
        <hr>
        <p><b>Autor Principal:</b> José David Pérez Zapata</p>
        <p><b>Asistencia:</b> Desarrollado con asistencia de IA (Gemini)</p>
        <p><b>Stack:</b> Python, PySide6, Pyserial, Mido</p>
        """
        QMessageBox.about(self, "Acerca de Control Okúa", info_texto)

    # --- SLOTS (Funciones de la GUI) ---

    def prompt_for_pin_and_open_config(self):
        """Pide un PIN antes de abrir la Configuración Avanzada."""
        pin, ok = QInputDialog.getText(self, 
                                       "Acceso Técnico Requerido", 
                                       "Ingrese el PIN de Técnico:", 
                                       QLineEdit.Password)
        
        if ok and pin == TECNICO_PIN:
            self.update_log("Acceso de Técnico concedido.", "green")
            dialog = ConfigDialog(self.config, self)
            
            if dialog.exec():
                self.config = dialog.get_config()
                self.save_config_to_file()
                self.update_log("Configuración guardada. Reinicie la aplicación para aplicar todos los cambios.", "green")
        elif ok:
            self.update_log("Error: PIN incorrecto.", "red")

    def prompt_for_pin_and_add_tab(self):
        """Pide un PIN antes de añadir una nueva pestaña de Maestro."""
        pin, ok = QInputDialog.getText(self, 
                                       "Acceso Técnico Requerido", 
                                       "Ingrese el PIN de Técnico:", 
                                       QLineEdit.Password)
        
        if ok and pin == TECNICO_PIN:
            self.update_log("Acceso de Técnico concedido. Añadiendo pestaña...", "green")
            self.add_maestro_tab()
        elif ok:
            self.update_log("Error: PIN incorrecto.", "red")

    def save_config_to_file(self):
        """Guarda la configuración actual en config.json persistente."""
        try:
            config_path = get_config_path()
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
            self.update_log(f"config.json guardado en {config_path}", "gray")
        except Exception as e:
            self.update_log(f"Error al guardar config.json: {e}", "red")

    def update_log(self, message, color):
        """Añade un mensaje al panel de log central"""
        hex_color = STATUS_COLORS.get(color, "black")
        self.log_box.append(f'<span style="color:{hex_color};">{message}</span>')

    @Slot(str)
    def release_midi_port(self, port_name):
        """Devuelve un nombre de puerto MIDI al pool cuando se cierra una pestaña."""
        if port_name and port_name not in self.available_midi_port_names:
            self.available_midi_port_names.append(port_name)
            self.update_log(f"Puerto '{port_name}' devuelto al pool.", "gray")

    def update_global_midi_activity(self, tab, msgs_per_sec):
        """Actualiza el contador MIDI global"""
        self.activity_counters[tab] = msgs_per_sec
        self.recalculate_global_activity()

    def recalculate_global_activity(self):
        total = sum(self.activity_counters.values())
        self.label_midi_activity.setText(f"Actividad MIDI Global: {total} msgs/seg")
        
    def request_com_port_lock(self, port_name):
        """
        Acionado por una pestaña hija ANTES de conectarse.
        Devuelve True si el puerto está libre, Falso si está ocupado.
        """
        if port_name in self.active_com_ports:
            return False
        else:
            self.active_com_ports.add(port_name)
            return True

    def release_com_port(self, port_name):
        """Llamado por una pestaña hija DESPUÉS de desconectarse."""
        if port_name in self.active_com_ports:
            self.active_com_ports.remove(port_name)
            self.update_log(f"Puerto {port_name} liberado.", "gray")
        
        for tab in self.maestro_tabs:
            if tab.btn_connect.isChecked() == False:
                tab.on_refresh_coms()

    def closeEvent(self, event):
        """Limpia todos los hilos al cerrar la ventana."""
        self.update_log("Cerrando aplicación... deteniendo todos los hilos...", "gray")
        for tab in self.maestro_tabs:
            tab.stop_worker()
        event.accept()