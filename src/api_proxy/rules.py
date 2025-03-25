"""
rules.py

En este archivo, se definen todas las reglas que nuestro Rate Limiter va a tener
TODO: No tener reglas que usen And (por ejemplo, IPAndPathRule), porque en el momento en el que queramos tener checkear 3 o 4 rules al mismo tiempo, va a ser un CAOS
"""

from pydantic import BaseModel, Field


class RateRuleBase(BaseModel):
    """Base para todas las reglas. Define los campos comunes."""

    # Segun la docu, Field se usa para añadir validaciones e info extra sobre un campo
    limit: int = Field(..., gt=0)
    window: int = Field(..., gt=0, description="TTL (Time To Live) de la regla, en segundos")


class IPRule(RateRuleBase):
    """
    Regla basada en el IP de origen
    """

    type: str = "ip"
    # Puedes añadir campos específicos para IP si es necesario


class PathRule(RateRuleBase):
    """
    Regla basada en el path al que se hace request
    """

    type: str = "path"
    pattern: str = Field(..., description="Patrón de ruta (ej: /items/*)")


class IPAndPathRule(RateRuleBase):
    """
    Regla basada en el IP de origen y a qué path se le hace request
    """

    type: str = "ip_path"
    pattern: str


# Unimos todos los tipos de reglas posibles
# Si en el futuro se quieren añadir reglas, no se olviden de ponerlas acá!
Rule = IPRule | PathRule | IPAndPathRule
