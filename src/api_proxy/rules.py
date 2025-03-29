"""
Módulo que define las reglas de rate limiting y su lógica asociada.
"""

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .utils import matches_pattern

logger = logging.getLogger("uvicorn.error")

# TODO: No está bueno que las subclases de Rule necesiten ip y path como parámetros, si no todas las usan.
# Puede ser que la mejor forma de hacerlo sea pasar un objeto, con **kwargs


class Rule(BaseModel):
    """
    Clase base abstracta para todas las reglas de rate limiting.
    Define los campos y métodos que deben implementar las subclases.

    Atributos:
        limit (int): Número máximo de peticiones permitidas en la ventana de tiempo.
        window (int): Duración de la ventana en segundos.
    """

    limit: int = Field(..., gt=0, description="Límite máximo de peticiones")
    window: int = Field(..., gt=0, description="Duración de la ventana en segundos")

    def matches(self, ip: str, path: str) -> bool:
        """
        Determina si la regla aplica a la combinación ip/path recibida.

        Args:
            ip (str): Dirección IP del cliente
            path (str): Ruta accedida

        Returns:
            bool: True si la regla aplica, False en caso contrario

        Raises:
            NotImplementedError: Si la subclase no implementa este método
        """
        raise NotImplementedError("Método abstracto: debe implementarse en subclases")

    def generate_key(self, ip: str, path: str) -> str:
        """
        Genera la clave única para identificar esta regla en Redis.

        Args:
            ip (str): Dirección IP del cliente
            path (str): Ruta accedida

        Returns:
            str: Clave Redis para el contador

        Raises:
            NotImplementedError: Si la subclase no implementa este método
        """
        raise NotImplementedError("Método abstracto: debe implementarse en subclases")


class IPRule(Rule):
    """
    Regla que aplica límites basados en una dirección IP específica.

    Atributos:
        type (Literal['ip']): Identificador del tipo de regla (fijo: 'ip')
        ip (str): Dirección IP a limitar (formato IPv4 válido)
    """

    type: Literal["ip"] = "ip"
    ip: str = Field(..., pattern=r"^\d{1,3}(\.\d{1,3}){3}$", example="192.168.1.1")

    def matches(self, ip: str, path: str) -> bool:
        """Verifica si la IP recibida coincide con la de la regla."""
        return ip == self.ip

    def generate_key(self, ip: str, path: str) -> str:
        """Genera clave en formato: limit:ip:{ip}"""
        return f"limit:ip:{self.ip}"


class PathRule(Rule):
    """
    Regla que aplica límites basados en un patrón de ruta.

    Atributos:
        type (Literal['path']): Identificador del tipo de regla (fijo: 'path')
        pattern (str): Patrón de ruta a coincidir (ej: '/items/*')
    """

    type: Literal["path"] = "path"
    pattern: str = Field(..., min_length=1, example="/items/*")

    def matches(self, ip: str, path: str) -> bool:
        """Verifica si la ruta recibida coincide con el patrón."""
        return matches_pattern(path, self.pattern)

    def generate_key(self, ip: str, path: str) -> str:
        """Genera clave en formato: limit:path:{pattern}"""
        return f"limit:path:{self.pattern}"


class IPPathRule(Rule):
    """
    Regla que aplica límites combinando una IP y patrón de ruta.

    Atributos:
        type (Literal['ip_path']): Identificador del tipo de regla (fijo: 'ip_path')
        ip (str): Dirección IP a limitar (formato IPv4 válido)
        pattern (str): Patrón de ruta a coincidir (ej: '/categories/*')
    """

    type: Literal["ip_path"] = "ip_path"
    ip: str = Field(..., pattern=r"^\d{1,3}(\.\d{1,3}){3}$", example="10.0.0.5")
    pattern: str = Field(..., min_length=1, example="/categories/*")

    def matches(self, ip: str, path: str) -> bool:
        """Verifica coincidencia de IP y ruta simultáneamente."""
        return ip == self.ip and matches_pattern(path, self.pattern)

    def generate_key(self, ip: str, path: str) -> str:
        """Genera clave en formato: limit:ip_path:{ip}:{pattern}"""
        return f"limit:ip_path:{self.ip}:{self.pattern}"


Rule = IPRule | PathRule | IPPathRule


def parse_rules(raw_data: dict[str, Any]) -> list[Rule]:
    """
    Convierte datos crudos (generalmente de YAML) en objetos Rule válidos.

    Args:
        raw_data (dict[str, Any]): Diccionario con estructura específica

    Returns:
        list[Rule]: Lista de reglas validadas

    Raises:
        KeyError: Si falta algún campo obligatorio
        ValidationError: Si hay valores inválidos

    Example:
        >>> data = {"rules": [{"type": "ip", "ip": "192.168.1.1", "limit": 100, "window": 60}]}
        >>> parse_rules(data)
        [IPRule(type='ip', ip='192.168.1.1', limit=100, window=60)]
    """
    parsed_rules = []
    for rule in raw_data.get("rules", []):
        try:
            rule_type = rule["type"]
            if rule_type == "ip":
                parsed_rules.append(IPRule(**rule))
            elif rule_type == "path":
                parsed_rules.append(PathRule(**rule))
            elif rule_type == "ip_path":
                parsed_rules.append(IPPathRule(**rule))
            else:
                logger.warning("Tipo de regla desconocido: %s - omitiendo", rule_type)
        except KeyError as e:
            logger.error("Campo faltante en regla: %s", e)
            raise
        except ValidationError as e:
            logger.error("Error validando regla: %s", e.json())
            raise
    return parsed_rules
