"""
Este módulo se encarga de cargar la configuración de nuestra app.

Este recibe la ubicación de un archivo config.yaml del cual obtener la configuración, y parsea este archivo
para transformarlo en una lista de Rules

Ver https://stackoverflow.com/questions/32923451/how-to-run-an-function-when-anything-changes-in-a-dir-with-python-watchdog
Y https://pythonhosted.org/watchdog/quickstart.html
"""

import logging
from pathlib import Path

# Para ver para que importamos pformat, ver https://stackoverflow.com/a/11093247/15965186
from pprint import pformat

import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .rules import Rule, parse_rules

# See https://stackoverflow.com/a/77007723/15965186
logger = logging.getLogger("uvicorn.error")


class ConfigLoader:
    """
    Clase responsable de cargar y recargar la config desde un archivo YAML.

    """

    def __init__(self, config_path: str):
        """
        Objeto para leer el archivo de configuración

        Args:
            config_path (str): Ruta del archivo de config.
        """
        self.config_path = config_path
        self.rules = self._load_config()

    def _load_config(self) -> list[Rule]:
        """
        Carga el archivo YAML y extrae la sección de reglas.

        Returns:
            dict: Diccionario con las reglas de configuración.
        """
        logger.info("Cargando el archivo de config: %s", self.config_path)
        # Si no especificamos el encoding, pylint se queja :(
        with open(self.config_path, encoding="utf-8") as f:
            loaded_rules = yaml.safe_load(f)
            logger.debug("REGLAS CARGADAS:\n%s", pformat(loaded_rules))

            # Parseamos las reglas, para convertirlas de un diccionario, a una lista de Rules como las de rules.py
            parsed_rules = parse_rules(loaded_rules)
            logger.debug("REGLAS PARSEADAS:\n%s", pformat(parsed_rules))

            return parsed_rules

    def reload(self) -> None:
        """Recarga el archivo de config actualizando las reglas."""
        self.rules = self._load_config()
        logger.info("Se recargaron las reglas, ahora son:\n%s", pformat(self.rules))


class ConfigWatcher:
    """
    Observa cambios en el archivo de config y ejecuta un callback cuando hay cambios.

    Para hacer el watch, usa la clase FileUpdateHandler, que observa una path y cada vez que se actualiza, llama a una función callback

    Esta clase NO se encarga de reloadear la config cargada en memoria, sino que espera que eso lo haga la función callback que sea pasada.
    O sea, se le debería pasar como callback una función reload() que recargue la config

    Args:
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

    def start(self) -> None:
        """Inicia la monitorización del archivo de config."""

        # Si algun día se implementa para que mire un directorio en vez de un solo archivo, quizas convenga poner recursive=false
        self.observer.schedule(
            self.handler,  # el handler DEBE ser un FileSystemEventHandler
            path=str(Path(self.config_path).parent),  # El path a monitorear
            recursive=False,  # Si recursive = true, monitorea subdirectorios
        )
        logging.info("Iniciando watcheo de %s", self.config_path)
        self.observer.start()

    def stop(self) -> None:
        """Detiene el watcheo y libera recursos."""
        # Se usa stop() y despues join() porque así está en la documentación
        self.observer.stop()
        self.observer.join()


class FileUpdateHandler(FileSystemEventHandler):
    """
    Handler de eventos para cambios en el archivo de configuración.

    Observa target_path, y cada vez que se actualiza llama a la función callback

    Se uso una clase aparte porque tenía que heredar de FileSystemEventHandler
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
