"""
rules.py

En este archivo, se definen todas las reglas que nuestro Rate Limiter va a tener
TODO: No tener reglas que usen And (por ejemplo, IPPathRule), porque en el momento en el que queramos tener checkear 3 o 4 rules al mismo tiempo, va a ser un CAOS
"""

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

# See https://stackoverflow.com/a/77007723/15965186
logger = logging.getLogger("uvicorn.error")


class RateRuleBase(BaseModel):
    """Base para todas las reglas. Define los campos comunes."""

    # Segun la docu, Field se usa para añadir validaciones e info extra sobre un campo
    limit: int = Field(..., gt=0)
    window: int = Field(..., gt=0, description="TTL (Time To Live) de la regla, en segundos")


class IPRule(RateRuleBase):
    """
    A rate limiting rule based on an IP address.

    Attributes:
        type (Literal["ip"]): A fixed value indicating this rule is IP-based.
        ip (str): The IP address to which the rule applies.
            The value must match the regex pattern "^\d{1,3}(\.\d{1,3}){3}$" ensuring it is in valid IPv4 format.
    """

    type: Literal["ip"] = "ip"
    ip: str = Field(..., pattern=r"^\d{1,3}(\.\d{1,3}){3}$")


class PathRule(RateRuleBase):
    """
    A rate limiting rule based on URL path matching.

    Attributes:
        type (Literal["path"]): A fixed value indicating this rule is path-based.
        pattern (str): A string representing the URL path pattern.
            The string must have a minimum length of 1, ensuring it is not empty.
    """

    type: Literal["path"] = "path"
    pattern: str = Field(..., min_length=1)


class IPPathRule(RateRuleBase):
    """
    A combined rate limiting rule based on both IP address and URL path.

    Attributes:
        type (Literal["ip_path"]): A fixed value indicating this rule combines IP and path criteria.
        ip (str): The IP address component of the rule.
            The value must match the regex pattern "^\d{1,3}(\.\d{1,3}){3}$" ensuring it is a valid IPv4 address.
        pattern (str): The URL path pattern component of the rule.
            The pattern must have a minimum length of 1 to ensure it is not empty.
    """  # noqa: W605

    type: Literal["ip_path"] = "ip_path"
    ip: str = Field(..., pattern=r"^\d{1,3}(\.\d{1,3}){3}$")
    pattern: str = Field(..., min_length=1)


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
