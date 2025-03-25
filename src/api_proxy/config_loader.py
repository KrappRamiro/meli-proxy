"""
Ver https://stackoverflow.com/questions/32923451/how-to-run-an-function-when-anything-changes-in-a-dir-with-python-watchdog
Y https://pythonhosted.org/watchdog/quickstart.html
"""

from pathlib import Path

import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class ConfigLoader:
    """
    Clase responsable de cargar y recargar la config desde un archivo YAML.

    Attributes:
        config_path (str): Ruta del archivo de config.
        rules (dict): Diccionario con las reglas cargadas del archivo.
    """

    def __init__(self, config_path: str):
        """Inicializa el cargador y lee el archivo de config."""
        self.config_path = config_path
        self.rules = self._load_config()

    def _load_config(self) -> dict:
        """
        Carga el archivo YAML y extrae la sección de reglas.

        Returns:
            dict: Diccionario con las reglas de configuración.
        """
        # Si no especificamos el encoding, pylint se queja :(
        with open(self.config_path, encoding="utf-8") as f:

            loaded_rules = yaml.safe_load(f)["rules"]
            print(f"REGLAS CARGADAS: {loaded_rules}")
            print(f"RULES TYPE: {type(loaded_rules)}")
            # TODO: Hacer que rules type sea mapeado a los tipos definidos en rules.py
            return loaded_rules

    def reload(self):
        """Recarga el archivo de config actualizando las reglas."""
        self.rules = self._load_config()
        print(f"REGLAS RECARGADAS: {self.rules}")


class ConfigWatcher:
    """
    watchea cambios en el archivo de config y ejecuta un callback cuando hay cambios.

    Attributes:
        observer (Observer): Instancia de Observer que mire cambios en el filesystem
        handler (FileUpdateHandler): handler cuando haya un evento onChange
    """

    def __init__(self, config_path: str, callback: callable):
        """
        Inicialización del ConfigWatcher.

        Args:
            config_path (str): Ruta del archivo a watchear.
            callback (callable): Función a ejecutar al detectar cambios.
        """

        # Observer (de watchdog) monitorea el archivo,
        # ver https://pythonhosted.org/watchdog/quickstart.html para un ejemplo
        self.observer = Observer()
        self.config_path = config_path
        self.handler = FileUpdateHandler(config_path, callback)

    def start(self):
        """Inicia la monitorización del archivo de config."""
        # Monitoriza solo el directorio padre sin recursividad
        self.observer.schedule(self.handler, path=str(Path(self.config_path).parent), recursive=False)
        self.observer.start()

    def stop(self):
        """Detiene la monitorización y libera recursos."""
        self.observer.stop()
        self.observer.join()


class FileUpdateHandler(FileSystemEventHandler):
    """
    Handler de eventos para cambios en el archivo de configuración.
    """

    def __init__(self, target_path: str, callback: callable):
        """
        Args:
            target_path (str): Ruta del archivo a watchear.
            callback (callable): Función a llamar cuando se detecten modificaciones en el archivo ubicado en target_path
        """
        self.target_path = target_path
        self.callback = callback

    def on_modified(self, event):
        """
        Método invocado cuando se detecta una modificación en el sistema de archivos.

        Explicación detallada de la verificación:
        Algunos sistemas operativos/editores generan múltiples eventos para una misma modificación.
        Ejemplo común:
        Al guardar un archivo, algunos editores:
           - Crean un archivo temporal
           - Borran el original
           - Renombran el temporal al nombre original
        Esto genera 3 eventos distintos pero relacionados

        Casos prácticos que evita esta verificación:
        a) Si hay otro archivo modificado en el mismo directorio (en caso de que en el futuro, target_path sea un directorio en vez de un solo archivo)
           - Solo reacciona si es EXACTAMENTE nuestro archivo de configuración
        b) En sistemas como macOS/Windows, a veces se generan eventos duplicados
           - Ej: evento de contenido modificado + evento de metadatos modificados

        El if actúa como filtro para evitar ese tipo de casos
        """

        # Verifica que la ruta del evento coincida con el archivo objetivo
        # Esto previene ejecuciones múltiples por eventos relacionados, ver docstring
        if event.src_path == self.target_path:
            self.callback()
