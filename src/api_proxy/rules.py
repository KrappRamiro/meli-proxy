"""
rules.py

En este archivo, se definen todas las reglas que nuestro Rate Limiter va a tener
TODO: No tener reglas que usen And (por ejemplo, IPPathRule), porque en el momento en el que queramos tener checkear 3 o 4 rules al mismo tiempo, va a ser un CAOS
"""

from pydantic import BaseModel, Field, ValidationError
from typing import Literal, Union, Dict, Any
import logging


class RateRuleBase(BaseModel):
    """Base para todas las reglas. Define los campos comunes."""

    # Segun la docu, Field se usa para añadir validaciones e info extra sobre un campo
    limit: int = Field(..., gt=0)
    window: int = Field(..., gt=0, description="TTL (Time To Live) de la regla, en segundos")


class IPRule(RateRuleBase):
    type: Literal["ip"] = "ip"
    value: str = Field(..., pattern=r"^\d{1,3}(\.\d{1,3}){3}$")


class PathRule(RateRuleBase):
    type: Literal["path"] = "path"
    pattern: str = Field(..., min_length=1)


class IPPathRule(RateRuleBase):
    type: Literal["ip_path"] = "ip_path"
    ip: str = Field(..., pattern=r"^\d{1,3}(\.\d{1,3}){3}$")
    path: str = Field(..., min_length=1)


# Unimos todos los tipos de reglas posibles
# Si en el futuro se quieren añadir reglas, no se olviden de ponerlas acá!
Rule = IPRule | PathRule | IPPathRule


def parse_rules(raw_data: dict[str, Any]) -> list[Rule]:
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
                logging.warning("Regla desconocida omitida: %s", {rule_type})
        except KeyError as e:
            logging.error("Regla inválida - falta campo: %s", e)
        except ValidationError as e:
            logging.error("Error de validación: %s", {e.json()})
    return parsed_rules
