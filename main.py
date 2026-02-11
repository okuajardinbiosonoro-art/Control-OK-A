import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

# --- ¡NUEVA FUNCIÓN DE AYUDA! ---
def resource_path(relative_path):
    """ Obtiene la ruta absoluta al recurso, funciona para dev y para PyInstaller """
    try:
        # PyInstaller crea una carpeta temporal y guarda la ruta en _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # No estamos empaquetados, la ruta es la de nuestro script
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)
# --- FIN DE LA FUNCIÓN DE AYUDA ---

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from gui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # --- ¡CAMBIO! Usar resource_path para encontrar el ícono ---
    ICON_PATH = resource_path(os.path.join("assets", "icons", "app_icon.ico"))
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
    else:
        print(f"Advertencia: No se encontró el ícono en {ICON_PATH}")
    # --- FIN DEL CAMBIO ---

    # --- ¡CAMBIO! Usar resource_path para encontrar el tema ---
    try:
        qss_path = resource_path(os.path.join("gui", "theme.qss"))
        with open(qss_path, "r", encoding="utf-8") as f:
            _style = f.read()
            app.setStyleSheet(_style)
    except Exception as e:
        print(f"No se pudo cargar el tema 'theme.qss': {e}")
    # --- FIN DEL CAMBIO ---

    window = MainWindow()
    window.show()
    sys.exit(app.exec())